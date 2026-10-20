"""LP-dual screen: which constraint families could improve the objective if relaxed."""
from ortools.linear_solver import pywraplp

_DUAL_TOLERANCE = 1e-7
_INT_INF = 2 ** 62


def _is_linear(ct):
    try:
        return ct.has_linear()
    except AttributeError:
        return ct.HasField("linear")


def _lp_from_cp_model(model):
    proto = model.Proto()
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise ValueError("GLOP not available")
    inf = solver.infinity()

    variables = []
    for var in proto.variables:
        domain = list(var.domain)
        variables.append(solver.NumVar(float(domain[0]), float(domain[-1]), ""))

    def always_true(ct):
        if not ct.has_bool_or() or len(ct.enforcement_literal):
            return False
        for literal in ct.bool_or.literals:
            domain = proto.variables[literal if literal >= 0 else ~literal].domain
            if len(domain) == 2 and domain[0] == domain[1] == (1 if literal >= 0 else 0):
                return True
        return False

    constraints = []
    for ct in proto.constraints:
        if always_true(ct):
            constraints.append(None)
            continue
        if not _is_linear(ct) or len(ct.enforcement_literal) or len(ct.linear.domain) != 2:
            raise ValueError("model has a constraint the LP screen cannot represent")
        lo, hi = ct.linear.domain
        row = solver.Constraint(
            -inf if lo <= -_INT_INF else float(lo),
            inf if hi >= _INT_INF else float(hi),
        )
        for var_index, coeff in zip(ct.linear.vars, ct.linear.coeffs):
            row.SetCoefficient(variables[var_index], float(coeff))
        constraints.append(row)

    objective = solver.Objective()
    for var_index, coeff in zip(proto.objective.vars, proto.objective.coeffs):
        objective.SetCoefficient(variables[var_index], float(coeff))
    objective.SetOffset(float(proto.objective.offset))
    objective.SetMinimization()
    return solver, constraints


def dual_screen(model, family_constraints):
    try:
        solver, constraints = _lp_from_cp_model(model)
        if solver.Solve() != pywraplp.Solver.OPTIMAL:
            return None
        scores = {}
        for key, indexes in family_constraints.items():
            total = sum(abs(constraints[i].dual_value()) for i in indexes)
            scores[key] = total if total > _DUAL_TOLERANCE else 0.0
        return scores
    except Exception:
        return None
