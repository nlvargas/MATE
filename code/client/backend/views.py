import json
import os
import re
import time

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from . import msft_auth
from .utils import (
    create_students,
    create_parms,
    count_options,
    upload_parms,
    compressStringToBytes,
    id_generator,
    student_type_key,
)
from model_common import estimate_variable_count
from io import BytesIO
from openpyxl import load_workbook


# Seconds run_model spends building/solving before the 0.9 "safety margin"
# baked into optimization.py / optimization_cpsat.py -- see SYNC_SOLVE_TMAX_SECONDS.
_SYNC_TIME_LIMIT_SAFETY_FACTOR = 0.90 * 60


@api_view(['POST'])
def upload(request):
    f = request.FILES['file']
    wb = load_workbook(filename=BytesIO(f.read()))
    attributes = request.POST["attributes"].split(",")
    if request.POST["modules"] == "":
        modules = []
    else:
        modules = request.POST["modules"].split(",")
    preferences_number = int(request.POST["preferencesNumber"])

    students, options = create_students(wb, attributes, modules, preferences_number)

    response = {"a": json.dumps(count_options(students, options)),
                "students": json.dumps([students[ob].__dict__ for ob in students])}
    return Response(response, status=status.HTTP_200_OK)


def _preference_outcome(sol, students_preferences_number):
    """
    Tally how many students landed in each preference rank (1st choice, 2nd
    choice, ..., or none of their ranked topics). Same job as
    code/server/utils.py's get_report() (used for the emailed/offline
    path) -- this view never imports that module (code/server is a
    separate, independently deployed project this one only ever talks to
    over SSH, never in-process -- see model_common.py's module docstring)
    -- but both key into `priority` the same way, via each side's own
    model_common.student_type_key() (imported here as student_type_key)
    instead of independently re-deriving the same key from an f-string,
    which used to be able to silently disagree (see that function's
    docstring).
    """
    priority = sol["priority"]
    values = {str(i): 0 for i in range(1, students_preferences_number + 1)}
    values["none"] = 0
    for group in sol["results"]:
        for student in group["students"]:
            type_id = student_type_key(
                student["attributes"], student["preferences"], student.get("disponibilities", [])
            )
            rank = priority.get(type_id, {}).get(group["group"])
            if rank is None or rank >= 100:
                values["none"] += 1
            else:
                values[str(rank)] = values.get(str(rank), 0) + 1
    return values


def _run_solver(data):
    """
    Import and call the CP-SAT solver's run_model(data). Imported lazily
    (not at module load time) so a missing ortools install only breaks the
    request that needed it, not the whole Django process. This app only
    ever runs CP-SAT in-process -- the Gurobi backend (code/server/
    optimization.py) is a separate, independently deployed project reached
    only by submitting a job to the cluster over SSH (see
    backend/utils.py's upload_parms()), never imported here.
    """
    try:
        from .optimization_cpsat import run_model
    except ImportError as e:
        raise RuntimeError(
            "Couldn't import the CP-SAT solver -- is ortools installed "
            "(see code/client/requirements.txt)?"
        ) from e
    return run_model(data)


@api_view(['POST'])
def run_model(request):
    params = json.loads(request.body.decode('utf-8'))
    data = create_parms(params)

    students_preferences_number = int(data["students_preferences_number"])

    # No closed-form pre-flight feasibility check runs here anymore: those
    # checks now run client-side, live, as the request is being configured
    # (see frontend/src/containers/CreateGroups.js's `issues` and
    # docs/ARCHITECTURE.md's Pre-flight feasibility checks subsection for
    # why -- catching an infeasible combination of parameters while it's
    # still being typed beats rejecting it after a round-trip). A request
    # that reaches this view has already passed those checks in the UI
    # that built it; a genuinely infeasible request still gets caught by
    # the solve itself, reported the same "causes" shape as below.

    # Estimated decision-variable count (model_common.
    # estimate_variable_count()), not raw student count, decides whether
    # this solves inline or goes to the cluster -- see
    # SYNC_SOLVE_MAX_VARIABLES's comment in project/settings.py for why.
    estimated_variables = estimate_variable_count(data)

    if estimated_variables <= settings.SYNC_SOLVE_MAX_VARIABLES:
        # Small problem: solve it inline and hand the result straight back.
        # The person can choose their own time budget on the Configure & run
        # screen (CreateGroups.js's slider, sent here as maxSolveSeconds,
        # seconds); a missing/invalid value falls back to the admin default.
        # Clamped server-side regardless of what the client sends -- a
        # tampered or stale request can't buy more solve time than this
        # deployment allows (see SYNC_SOLVE_TMAX_MIN/MAX_SECONDS's comment
        # in project/settings.py for why the ceiling has to stay where it
        # is: API Gateway / Lambda's 29s hard request timeout).
        try:
            requested_tmax_seconds = float(params.get("maxSolveSeconds"))
        except (TypeError, ValueError):
            requested_tmax_seconds = settings.SYNC_SOLVE_TMAX_SECONDS
        tmax_seconds = min(
            max(requested_tmax_seconds, settings.SYNC_SOLVE_TMAX_MIN_SECONDS),
            settings.SYNC_SOLVE_TMAX_MAX_SECONDS,
        )
        data["tmax"] = tmax_seconds / _SYNC_TIME_LIMIT_SAFETY_FACTOR
        started = time.monotonic()
        try:
            sol = _run_solver(data)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        solve_time = time.monotonic() - started

        if not sol["factible"]:
            return Response({
                "queued": False,
                "factible": False,
                "status": sol.get("status"),
                "solve_time": solve_time,
                # Populated by optimization_cpsat.py's deletion-filter search
                # (see its module docstring); empty for the Gurobi backend,
                # which doesn't compute this yet -- the frontend falls back
                # to a generic message when this is empty.
                "causes": sol.get("causes", []),
            }, status=status.HTTP_200_OK)

        groups = [
            {
                "group": g["group"],
                "group_name": g["group_name"],
                "students": g["students"],
                "size": len(g["students"]),
            }
            for g in sol["results"]
        ]
        return Response({
            "queued": False,
            "factible": True,
            "status": sol.get("status"),
            "solve_time": solve_time,
            "groups": groups,
            "preference_outcome": _preference_outcome(sol, students_preferences_number),
            "students_preferences_number": students_preferences_number,
        }, status=status.HTTP_200_OK)

    # Large problem: hand off to the cluster -- a shared, licensed resource
    # (Gurobi seat + compute on the PUC cluster), so this branch alone is
    # gated on a signed-in @uc.cl/@ing.puc.cl session (see msft_auth.py).
    # The sync path above never reaches this check: it's free, open-source,
    # and runs on this app's own Lambda, so it stays open to anyone.
    if not msft_auth.session_email_allowed(request.session):
        return Response({
            "error": "auth_required",
            "message": (
                "This roster is large enough to need the cluster. Sign in "
                "with a uc.cl or ing.puc.cl account to submit it."
            ),
        }, status=status.HTTP_403_FORBIDDEN)

    # Results are emailed once the Slurm job finishes.
    ID = id_generator()
    data["ID"] = ID
    data_string = json.dumps(data)
    compressed_data_string = compressStringToBytes(data_string)
    upload_parms(compressed_data_string, ID)
    return Response({"queued": True}, status=status.HTTP_200_OK)


@api_view(['POST'])
def sensitivity(request):
    """
    On-demand "what's each requirement costing you" analysis for the
    Results screen -- takes the same request body run_model() does and
    re-solves the roster once per user-configurable constraint family,
    dropped one at a time, to rank how much each is costing in #1-choice
    placements. See optimization_cpsat.sensitivity_report()'s docstring
    for why this has to be a separate, on-demand call rather than
    something bundled into run_model() itself (it would reopen the exact
    wall-clock-budget problem run_model() was fixed for -- see that
    function's docstring -- if it ran on every request instead of only
    when asked for).

    Sync-only, same SYNC_SOLVE_MAX_VARIABLES cap run_model()'s inline path
    uses: a roster too large to solve inline is too large to run this
    analysis on top of that solve, too. CP-SAT only, not "for now" but by
    design -- this app only ever runs CP-SAT in-process (see _run_solver()),
    and the Gurobi backend's cluster/async path has no on-demand analysis
    like this one at all, same reason it has no find_infeasibility_causes()
    (see run_model()'s "causes" comment).
    """
    params = json.loads(request.body.decode('utf-8'))
    data = create_parms(params)
    estimated_variables = estimate_variable_count(data)

    if estimated_variables > settings.SYNC_SOLVE_MAX_VARIABLES:
        return Response({
            "error": "too_large",
            "message": "Sensitivity analysis is only available for rosters solved inline.",
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        from .optimization_cpsat import sensitivity_report
        report = sensitivity_report(data)
    except ImportError as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(report, status=status.HTTP_200_OK)


@api_view(['GET'])
def remove_params_from_queue(request, params_id):
    # params_id must match id_generator()'s output format exactly (6 chars,
    # uppercase A-Z/0-9) before it's used to build a filesystem path below --
    # otherwise a crafted params_id could traverse outside the
    # model_params/{pending,done} directories.
    if not re.fullmatch(r"[A-Z0-9]{6}", params_id):
        return Response({"error": "invalid params_id"}, status=status.HTTP_400_BAD_REQUEST)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.replace(f"{BASE_DIR}/data/model_params/pending/{params_id}.json",
               f"{BASE_DIR}/data/model_params/done/{params_id}.json")
    return Response({"removed": params_id}, status=status.HTTP_200_OK)
