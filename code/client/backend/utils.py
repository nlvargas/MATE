from collections import OrderedDict
import gzip
import os

from model_common import student_type_key
from io import BytesIO
from scp import SCPClient
import paramiko
import string
import random


class Student:
    def __init__(self, id, attributes, preferences, modelAttributes, modelPreferences,disponibilities):
        self.id = id
        self.attributes = attributes
        self.preferences = preferences
        self.modelAttributes = modelAttributes
        self.modelPreferences = modelPreferences
        self.answered = False if 'None' in list(modelPreferences.values()) else True
        self.disponibilities = disponibilities
        self.flexibility = 1
        self.a = {}

    def __repr__(self):
        return "{}: Atributos: {} - Preferencias: {} - Disponibilidad: {}"\
               .format(self.id, self.attributes, self.preferences, self.a)

    def __str__(self):
        return self.__repr__()

    def get_disponibility(self, disponibilities_name):
        for i, j in zip(disponibilities_name, self.disponibilities):
            if j == 1:
                self.flexibility += 1
            if j != "#N/A":
                self.a[i] = int(j)
            else:
                self.a[i] = 1

class StudentType:
    def __init__(self, id, attributes, preferences, disponibilities, a):
        self.id = id
        self.attributes = attributes
        self.preferences = preferences
        self.disponibilities = disponibilities
        self.flexibility = sum(int(i) for i in disponibilities)
        self.answered = False if ('None' in list(preferences.values())) or ('#N/A' in list(preferences.values())) else True
        self.students = 1
        self.students_list = []
        self.a = a
    
    def __str__(self):
        return str(self.id)


def upload_parms(bytes, ID):
    # Cluster SSH credentials live in code/client/.env (loaded into
    # os.environ by settings.py via django-environ at process start), not in
    # source -- see .env.example for the keys this expects.
    HOST = os.environ.get("MATE_CLUSTER_HOST", "cluster.ing.uc.cl")
    USER = os.environ.get("MATE_CLUSTER_USER", "nlvargas")
    PASSWORD = os.environ.get("MATE_CLUSTER_PASSWORD")
    if not PASSWORD:
        raise RuntimeError(
            "MATE_CLUSTER_PASSWORD is not set -- add it to code/client/.env "
            "(see .env.example) before submitting a job to the cluster."
        )
    PARAMS_PATH = os.environ.get("MATE_CLUSTER_PARAMS_PATH", "/home/nlvargas/groups/params")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Optional project-local known_hosts file, in addition to whatever's
    # already in the deploying user's own ~/.ssh/known_hosts (loaded above
    # by load_system_host_keys()) -- lets a deployment pin the cluster's
    # host key explicitly without requiring every operator to have SSH'd to
    # it by hand first. Not added to .env.example because it's optional:
    # left unset, this just falls back to load_system_host_keys() alone.
    known_hosts_path = os.environ.get("MATE_CLUSTER_KNOWN_HOSTS")
    if known_hosts_path:
        client.load_host_keys(known_hosts_path)
    # RejectPolicy (paramiko's safe default) refuses to connect to a host
    # whose key isn't already known via the sources above -- unlike the
    # AutoAddPolicy this replaced, it will never silently trust+cache
    # whatever key a server presents on first connect, which offered no
    # protection against a swapped/spoofed host. This does mean the
    # deploying user's ~/.ssh/known_hosts (or MATE_CLUSTER_KNOWN_HOSTS, if
    # set) must already contain the cluster's host key -- e.g. from having
    # SSH'd to it manually once -- before this will connect.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(HOST, 22, USER, PASSWORD)
    with SCPClient(client.get_transport(), socket_timeout=2*60) as scp:
        fl = BytesIO()
        fl.write(bytes)
        fl.seek(0)
        scp.putfo(fl, f'{PARAMS_PATH}/{ID}_params.txt')
        fl.close()
    stdin, stdout, stderr = client.exec_command(f"sbatch groups/run.sh {ID}")
    client.close()


def compressStringToBytes(inputString):
  """
  read the given string, encode it in utf-8,
  compress the data and return it as a byte array.
  """
  bio = BytesIO()
  bio.write(inputString.encode("utf-8"))
  bio.seek(0)
  stream = BytesIO()
  compressor = gzip.GzipFile(fileobj=stream, mode='w')
  while True:  # until EOF
    chunk = bio.read(8192)
    if not chunk:  # EOF?
      compressor.close()
      return stream.getvalue()
    compressor.write(chunk)


def create_students(wb, attributes, modules, preferences_number):
    options = {attr: set() for attr in attributes}
    ws = wb.active
    students = {}
    parameters = ["student_fk"] + \
                [a for a in attributes] + \
                [d for d in modules] + \
                [p for p in range(1, preferences_number + 1)]
    for row in ws.iter_rows(min_row=2, min_col=0, max_col=len(parameters)):
        p = OrderedDict()
        null_count = 0
        for i in range(0, len(parameters)):
            if i in range(1, len(attributes) + 1):
                options[parameters[i]].add(str(row[i].value))
            p[parameters[i]] = str(row[i].value)
            if row[i].value is None:
                null_count += 1
        if null_count >= len(parameters):
            break

        attr = {}
        for a in attributes:
            attr[a] = p[a]
        prefs = {}
        for i, pref in enumerate([p[pref] for pref in range(1, preferences_number + 1)]):
            prefs[i + 1] = pref
        s = Student(p["student_fk"],
                    [p[a] for a in attributes],
                    [p[pref] for pref in range(1, preferences_number + 1)],
                    attr,
                    prefs, 
                    [p[d] for d in modules])
        if modules:
            s.get_disponibility(modules)
        students[s.id] = s
    return students, options


def count_options(students, options):
    attributes = {}
    for id in students:
        for a in students[id].attributes:
            if a not in attributes:
                attributes[a] = 1
            else:
                attributes[a] += 1
    opts = {attr: {} for attr in options}
    for attr in options:
        for opt in options[attr]:
            if opt != "None":
                opts[attr][opt] = attributes[opt]
    return opts


def create_students_types(students, options, attributes_list):
    types = {}
    for idx in students:
        student = students[idx]
        attributes = student["attributes"]
        preferences = student["preferences"]
        disponibilities = student["disponibilities"]
        a = student["a"]
        student_type_id = student_type_key(attributes, preferences, disponibilities)
        if student_type_id in types:
            types[student_type_id]["students"] += 1
        else:
            types[student_type_id] = StudentType(
                student_type_id,
                attributes,
                preferences,
                disponibilities,
                a,
            ).__dict__
        types[student_type_id]["students_list"].append(idx)
    
    students_types_attr = {}
    for i in types:
        students_types_attr[i] = {x: 0 for x in options}
        student_type = types[i]
        # student_type["attributes"] is {attr_name: value, ...} -- iterate
        # it directly by (name, value) pairs instead of zipping it
        # positionally against attributes_list (the caller's separately
        # built attribute-name list). The previous zip()-based version only
        # produced the right key because attributes_list and this dict's
        # key order happened to line up 1:1 -- iterating .items() says the
        # same thing without depending on two independently-built
        # sequences staying in identical order. attributes_list is no
        # longer needed here as a result.
        for attr, char in student_type["attributes"].items():
            students_types_attr[i][f"{attr}:{char}"] = 1
    return types, students_types_attr


def create_attributes(data):
    attributes = {}
    for attr in data["options"]:
        attributes[attr] = {}
        for opt in data["options"][attr]:
            # Keyed by "attr:opt" (the same attribute-value convention as
            # params["A"] / students_types_attr -- see create_students_types()
            # above and docs/ARCHITECTURE.md section 4's `R` set), not by the
            # bare option string: two different attributes can share a value
            # label (e.g. two Yes/No attributes), and a bare-value key would
            # collapse their bounds together. Must match the key format
            # CreateGroups.js's `bounds` state uses on the wire, exactly.
            bounds_key = f"{attr}:{opt}"
            if bounds_key in data["bounds"]:
                attributes[attr][opt] = data["bounds"][bounds_key]
                if attributes[attr][opt]["min"] == "Min":
                    attributes[attr][opt]["min"] = 0
                if attributes[attr][opt]["max"] == "Max":
                    attributes[attr][opt]["max"] = int(data['maxStudents'])
            else:
                attributes[attr][opt] = {
                    "min": 0, 
                    "max": int(data['maxStudents']), 
                    "solo": False,
                }
    return attributes


def create_students_dict(data, options):
    for i in data["students"]:
        i["attributes"] = i["modelAttributes"]
        i["preferences"] = i["modelPreferences"]
        i["answered"] = False if i["preferences"]["1"] == "#N/A" else True

    student_attr = {}
    for i in data["students"]:
        student_attr[i["id"]] = {x: 0 for x in options}
        for j in i["attributes"]:
            student_attr[i["id"]][i["attributes"][j]] = 1
    students = {x['id']: x for x in data["students"]}

    for s in students:
        a = {}
        for i, m in enumerate(data["modules"]):
            a[m] = students[s]["disponibilities"][i]
        students[s]["a"] = a

    return students, student_attr


def create_preferences(data):
    preferences = {}
    for p in data['preferences']:
        if p in data['prefsBounds']:
            preferences[p] = data['prefsBounds'][p]
        else:
            preferences[p] = {"min": 0, "max": data['groupsNumber']}
    return preferences


def create_parms(data):
    attributes_dict = create_attributes(data)
    attributes = data["attributes"]
    options = [f"{attr}:{char}" for attr in attributes_dict for char in attributes_dict[attr]]
    students, student_attr = create_students_dict(data, options)
    preferences = create_preferences(data)
    students_types, students_types_attr = create_students_types(students, options, attributes)
    data['fixedDay'].pop("module", None)
    data['fixedDay'].pop("mod", None)
    params = {
        'attributes': attributes_dict,
        'preferences': preferences,
        'groups_number': data['groupsNumber'],
        'lower_number': data['minStudents'],
        'upper_number': data['maxStudents'],
        'student_attr': student_attr,
        'students_preferences_number': data["preferencesNumber"],
        'students': students,
        'capacity': data['capacity'],
        'modules': data['modules'],
        'email': data['email'],
        'A': options,
        'tmax': int(data['tmax']),
        'sameDay': data['sameDay'],
        'fixedDay': data['fixedDay'],
        'students_types': students_types,
        'students_types_attr': students_types_attr,
        "usedPreferences": data["usedPreferences"]
    }
    return params


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    # Collision risk: no check against already-queued job IDs before
    # upload_parms() writes `{ID}_params.txt` on the cluster -- a collision
    # would silently overwrite another pending job's params file. Left as
    # size=6 with no collision-check-and-retry loop against remote SSH
    # state (that would add real complexity -- an extra SSH round-trip --
    # and a new failure mode, for a very low-probability event): at 36
    # possible chars, size=6 is 36**6 (~2.18 billion) possible IDs, so even
    # a few dozen simultaneously *queued* cluster jobs collide with
    # negligible probability (birthday bound).
    #
    # `size`/`chars` can't be casually widened to add more entropy either:
    # views.py's remove_params_from_queue() validates params_id against a
    # hardcoded r"[A-Z0-9]{6}" (a path-traversal guard on a local file
    # path), so this exact format is a cross-file contract -- a length or
    # charset change here needs a matching change in views.py.
    return ''.join(random.choice(chars) for _ in range(size))