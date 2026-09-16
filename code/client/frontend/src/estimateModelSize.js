/**
 * Rough, client-side estimate of the solved model's size -- run entirely
 * from data the Configure & run screen already has (the uploaded roster,
 * plus whatever's currently configured), no server round-trip needed.
 *
 * Mirrors two things the backend computes for real once a solve is
 * actually requested: how many distinct student types the roster
 * collapses into (see docs/ARCHITECTURE.md's Preprocessing section), and
 * how many candidate groups get built from the configured topics/sections.
 * From those two counts it sums up an approximate decision-variable count
 * across every variable family the model declares. It's an estimate, not
 * an exact count -- in particular, the type-to-group assignment variable
 * is sparse (a type only gets a variable for a group whose section it's
 * actually available for), so this approximates that sparsity with an
 * average availability fraction across the roster rather than replaying
 * the model's own indexing exactly.
 */

function studentTypeKey(student) {
  const attrKey = Object.entries(student.attributes || {})
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${k}=${v}`)
    .join(",");
  const prefKey = Object.entries(student.preferences || {})
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${k}=${v}`)
    .join(",");
  const dispo = student.disponibilities && student.disponibilities.length
    ? student.disponibilities.join(",")
    : "";
  return `${attrKey}|${prefKey}|${dispo}`;
}

function countStudentTypes(students) {
  return new Set(students.map(studentTypeKey)).size;
}

// Same shape create_preferences() (code/client/backend/utils.py) builds:
// a configured prefsBounds entry when present, otherwise {min: 0, max:
// groupsNumber}.
function prefBoundFor(prefsBounds, p, groupsNumber) {
  const b = prefsBounds[p];
  return {
    min: b && b.min != null ? b.min : 0,
    max: b && b.max != null ? b.max : groupsNumber,
  };
}

// Mirrors model_common.preprocessing()'s candidate-group count: with no
// sections configured, each topic contributes up to its configured max
// number of groups; with sections configured, each (topic, section) pair
// gets its own count, sized off how many students are available for that
// section (floor(availability / upper_number) + 1) and clamped into the
// topic's configured [min, max] group-count band.
function countCandidateGroups({ students, modules, preferences, prefsBounds, groupsNumber, upperNumber }) {
  if (!modules.length) {
    return preferences.reduce((sum, p) => sum + prefBoundFor(prefsBounds, p, groupsNumber).max, 0);
  }
  const availabilityByModule = modules.map((_, i) =>
    students.filter((s) => Number(s.disponibilities[i]) === 1).length
  );
  let total = 0;
  preferences.forEach((p) => {
    const { min, max } = prefBoundFor(prefsBounds, p, groupsNumber);
    availabilityByModule.forEach((disp) => {
      let n = Math.floor(disp / Math.max(1, upperNumber)) + 1;
      if (n < min) n = min;
      if (n > max) n = max;
      total += Math.max(0, n);
    });
  });
  return total;
}

// Weighted (by student, not by type) fraction of configured sections the
// average student is available for -- used to discount the sparse type x
// group assignment variable when sections are configured.
function averageAvailabilityFraction(students, modules) {
  if (!modules.length || !students.length) return 1;
  let sum = 0;
  students.forEach((s) => {
    const available = modules.reduce((acc, _, i) => acc + (Number(s.disponibilities[i]) === 1 ? 1 : 0), 0);
    sum += available / modules.length;
  });
  return sum / students.length;
}

export function estimateModelSize({
  students, modules, preferences, prefsBounds, options,
  groupsNumber, upperNumber,
}) {
  const typesCount = countStudentTypes(students);
  const groupsCount = countCandidateGroups({
    students, modules, preferences, prefsBounds, groupsNumber, upperNumber,
  });
  const attrValuesCount = Object.keys(options || {})
    .reduce((sum, attr) => sum + Object.keys(options[attr] || {}).length, 0);
  const availFraction = averageAvailabilityFraction(students, modules);

  const yEstimate = modules.length
    ? Math.round(typesCount * groupsCount * availFraction)
    : typesCount * groupsCount;
  const w = groupsCount;
  const z = typesCount + 1; // + z_max
  // Q[g, attr] and P[g, attr] are both dense over every (group, attribute
  // value) pair on the backend (see optimization_cpsat.py's _build_vars())
  // -- P isn't limited to "solo"-flagged values, it's declared for all of
  // them, even though only solo-flagged ones ever get a constraint that
  // uses it.
  const q = groupsCount * attrValuesCount;
  const p = groupsCount * attrValuesCount;
  const m = groupsCount + 1; // + m_max
  const topicSection = modules.length ? preferences.length * modules.length + preferences.length : 0;

  const variablesEstimate = yEstimate + w + z + q + p + m + topicSection;

  return { typesCount, groupsCount, variablesEstimate };
}
