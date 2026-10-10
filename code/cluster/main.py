import os
import sys
import traceback
from optimization import run_model
from utils import get_data, send_mail, send_admin_mail, send_error_mail, create_excel


ADMIN_EMAIL = "nlvargas@uc.cl"


def run(ID):
    print("Calling main")
    data = None
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
            send_admin_mail(ADMIN_EMAIL, xlsx_filepath=xlsx_filepath, txt_filepath=txt_filepath)
        else:
            send_mail(data["email"])
    except:
        print(traceback.format_exc())
        # data may never have been bound (e.g. get_data(ID) itself raised on
        # a corrupt/missing params file) -- fall back to notifying the admin
        # instead of crashing this handler with an UnboundLocalError/KeyError
        # and masking the real failure.
        if data is not None and "email" in data:
            send_error_mail(data["email"])
        else:
            send_error_mail(ADMIN_EMAIL)


if __name__ == "__main__":
    ID = sys.argv[1:][0]
    run(ID)
