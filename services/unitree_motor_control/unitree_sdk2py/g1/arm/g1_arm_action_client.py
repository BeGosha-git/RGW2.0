import json

from ...rpc.client import Client
from .g1_arm_action_api import (
    ARM_ACTION_API_VERSION,
    ARM_ACTION_SERVICE_NAME,
    ROBOT_API_ID_ARM_ACTION_EXECUTE_ACTION,
    ROBOT_API_ID_ARM_ACTION_GET_ACTION_LIST,
)

action_map = {
    "release arm": 99,
    "two-hand kiss": 11,
    "left kiss": 12,
    "right kiss": 13,
    "hands up": 15,
    "clap": 17,
    "high five": 18,
    "hug": 19,
    "heart": 20,
    "right heart": 21,
    "reject": 22,
    "right hand up": 23,
    "x-ray": 24,
    "face wave": 25,
    "high wave": 26,
    "shake hand": 27,
}


class G1ArmActionClient(Client):
    def __init__(self):
        super().__init__(ARM_ACTION_SERVICE_NAME, False)

    def Init(self):
        self._SetApiVerson(ARM_ACTION_API_VERSION)
        self._RegistApi(ROBOT_API_ID_ARM_ACTION_EXECUTE_ACTION, 0)
        self._RegistApi(ROBOT_API_ID_ARM_ACTION_GET_ACTION_LIST, 0)

    def ExecuteAction(self, action_id: int):
        payload = json.dumps({"data": action_id})
        code, _ = self._Call(ROBOT_API_ID_ARM_ACTION_EXECUTE_ACTION, payload)
        return code

    def GetActionList(self):
        payload = json.dumps({})
        code, data = self._Call(ROBOT_API_ID_ARM_ACTION_GET_ACTION_LIST, payload)
        if code == 0:
            return code, json.loads(data)
        return code, None

