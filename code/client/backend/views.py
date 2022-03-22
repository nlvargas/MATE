from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .utils import (
    create_students, 
    create_parms, 
    count_options, 
    upload_parms, 
    compressStringToBytes, 
    id_generator
)
from io import BytesIO
from openpyxl import load_workbook
import json
import os


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


@api_view(['POST'])
def run_model(request):
    params = json.loads(request.body.decode('utf-8'))
    ID = id_generator()
    data = create_parms(params)
    data["ID"] = ID
    data_string = json.dumps(data)
    compressed_data_string = compressStringToBytes(data_string)
    upload_parms(compressed_data_string, ID)
    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
def remove_params_from_queue(request, params_id):
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.replace(f"{BASE_DIR}/data/model_params/pending/{params_id}.json", 
               f"{BASE_DIR}/data/model_params/done/{params_id}.json")
