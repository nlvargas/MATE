import os
import sys
import traceback
from optimization import run_model
from utils import get_data, send_mail, send_admin_mail, send_error_mail, create_excel


def run(ID):
    print("Calling main")
    try:
        data = get_data(ID)
        sol = run_model(data)
        if sol["factible"]:
            BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filename = f"{ID}_results.xlsx"
            xlsx_filepath = f"{BASE_DIR}/groups/outputs/{filename}"
            txt_filepath = f"{BASE_DIR}/groups/outputs/result.txt"
            modules = data["modules"]
            students_preferences_number = int(data['students_preferences_number'])
            attributes = list(data["attributes"].keys())
            create_excel(sol, modules, students_preferences_number, attributes, xlsx_filepath)
            send_mail(data["email"], filepath=xlsx_filepath)
            send_admin_mail("nlvargas@uc.cl", xlsx_filepath=xlsx_filepath, txt_filepath=txt_filepath)
        else:
            send_mail(data["email"])
    except:
        print(traceback.format_exc())
        send_error_mail(data["email"])


if __name__ == "__main__":
    ID = sys.argv[1:][0]
    run(ID)
