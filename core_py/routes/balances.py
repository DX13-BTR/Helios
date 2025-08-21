from fastapi import APIRouter
import os
from core_py.modules.fss.starling.client import get_account_balance, get_spaces
from core_py.modules.fss.starling.transform import transform_starling_to_helios

router = APIRouter()

@router.get("/balances/current")
def get_current_balances():
    accounts = [
        {
            "name": "Efkaristo",
            "type": "business",
            "token": os.getenv("EFK_STARLING_TOKEN"),
            "account_uid": os.getenv("EFK_ACCOUNT_UID"),
        },
        {
            "name": "Personal",
            "type": "personal",
            "token": os.getenv("PERS_STARLING_TOKEN"),
            "account_uid": os.getenv("PERS_ACCOUNT_UID"),
        },
    ]

    result = {}

    for acct in accounts:
        try:
            balance = get_account_balance(acct["account_uid"], acct["token"])
            spaces = get_spaces(acct["account_uid"], acct["token"], acct["type"])
            snapshot = transform_starling_to_helios(balance, spaces, acct["name"])
            result[acct["name"].lower()] = snapshot
        except Exception as e:
            result[acct["name"].lower()] = {"error": str(e)}

    return result
