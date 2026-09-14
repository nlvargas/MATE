import json
import os
import time

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .utils import (
    create_students,
    create_parms,
    count_options,
    upload_parms,
    compressStringToBytes,
    id_generator,
    student_type_key,
)
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
    if request.POST["modules"] in ([], ""):
        modules = []
    else:
        modules = request.POST["modules"].split(",")
    preferences_number = int(request.POST["preferencesNumber"][0])

    students, options = create_students(wb, attributes, modules, preferences_number)

    response = {"a": json.dumps(count_options(students, options)),
                "students": json.dumps([students[ob].__dict__ for ob in students])}
    return Response(response, status=status.HTTP_200_OK)


def _preference_outcome(sol, students_preferences_number):
    """
    Tally how many students landed in each preference rank (1st choice, 2nd
    choice, ..., or none of their ranked topics). Same job as
    code/server/utils.py's get_report() (used for the emailed/offline
    path) -- this view doesn't import that module directly, since its bare
    name collides with this package's own utils.py (see the comment on
    SERVER_DIR in project/settings.py) -- but both now key into `priority`
    via the shared model_common.student_type_key() (imported here as
    student_type_key) instead of each independently re-deriving the same
    key from an f-string, which used to be able to silently disagree (see
    that function's docstring).
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


def _run_solver(solver_name, data):
    """
    Import and call the configured solver's run_model(data). Imported lazily
    (not at module load time) so an unconfigured/missing solver only breaks
    the request that needed it, not the whole Django process -- and so the
    default CP-SAT path never requires gurobipy to be importable at all.
    """
    if solver_name == "gurobi":
        try:
            from optimization import run_model
        except ImportError as e:
            raise RuntimeError(
                "MATE_SOLVER is set to 'gurobi' but gurobipy isn't installed/licensed "
                "in this environment."
            ) from e
    else:
        try:
            from optimization_cpsat import run_model
        except ImportError as e:
            raise RuntimeError(
                "Couldn't import the CP-SAT solver -- is ortools installed "
                "(see code/server/requirements.txt)?"
            ) from e
    return run_model(data)


@api_view(['POST'])
def run_model(request):
    params = json.loads(request.body.decode('utf-8'))
    data = create_parms(params)

    total_students = len(data["students"])
    students_preferences_number = int(data["students_preferences_number"])

    if total_students <= settings.SYNC_SOLVE_MAX_STUDENTS:
        # Small problem: solve it inline and hand the result straight back.
        data["tmax"] = settings.SYNC_SOLVE_TMAX_SECONDS / _SYNC_TIME_LIMIT_SAFETY_FACTOR
        started = time.monotonic()
        try:
            sol = _run_solver(settings.OPTIMIZER_SOLVER, data)
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

    # Large problem: hand off to the cluster, same as before -- results are
    # emailed once the Slurm job finishes.
    ID = id_generator()
    data["ID"] = ID
    data_string = json.dumps(data)
    compressed_data_string = compressStringToBytes(data_string)
    upload_parms(compressed_data_string, ID)
    return Response({"queued": True}, status=status.HTTP_200_OK)


@api_view(['GET'])
def remove_params_from_queue(request, params_id):
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.replace(f"{BASE_DIR}/data/model_params/pending/{params_id}.json",
               f"{BASE_DIR}/data/model_params/done/{params_id}.json")
