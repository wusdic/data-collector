"""
engine/user_integration.py
用户模块与主流程集成
"""

import logging
from persistence.bitable_manager import BitableManager

logger = logging.getLogger('engine.user_integration')

# 用户模块的 app_token（固定）
USER_APP_TOKEN = "BDxubmpjiaayMvs0mbucIyZunQd"

USER_TABLES = {
    "users": "tbl6Tu5D2zGGN1t1",
    "companies": "tbleLOfGtDWlmXp9",
    "materials": "tbl7dNo2JPUJbAVV",
    "related_info": "tblDWdkfB82Bfsj8",
}


class UserIntegration:
    """
    用户模块与主流程的集成层。

    封装对用户模块飞书表（app_token=BDxubmpjiaayMvs0mbucIyZunQd）的所有操作，
    提供业务级别的查询接口，供 engine 其他模块调用。
    """

    def __init__(self):
        self.bitable = BitableManager()
        self.bitable.app_token = USER_APP_TOKEN

    # ─── 单位查询 ────────────────────────────────────────────

    def get_all_companies(self) -> list:
        """获取所有单位"""
        return self.bitable.query(USER_TABLES["companies"])

    def get_company_profile(self, company_name: str) -> dict:
        """获取单位画像（基本信息）"""
        companies = self.bitable.query(
            USER_TABLES["companies"],
            filter={"field_name": "单位名称", "operator": "is", "value": [company_name]},
        )
        return companies[0] if companies else {}

    def get_company_materials(self, company_name: str) -> list:
        """获取单位材料（材料库）"""
        return self.bitable.query(
            USER_TABLES["materials"],
            filter={"field_name": "单位名称", "operator": "is", "value": [company_name]},
        )

    def get_company_related_info(self, company_name: str) -> list:
        """获取单位关联信息"""
        return self.bitable.query(
            USER_TABLES["related_info"],
            filter={"field_name": "单位名称", "operator": "is", "value": [company_name]},
        )

    def get_company_full_profile(self, company_name: str) -> dict:
        """
        获取单位完整画像（基本信息 + 材料 + 关联信息）。
        供适用性匹配阶段查询目标单位用。
        """
        return {
            "profile": self.get_company_profile(company_name),
            "materials": self.get_company_materials(company_name),
            "related_info": self.get_company_related_info(company_name),
        }

    # ─── 写入操作 ────────────────────────────────────────────

    def add_company(self, company_data: dict) -> str:
        """新增单位记录，返回 record_id"""
        return self.bitable.write_record(USER_TABLES["companies"], company_data)

    def add_related_info(self, info_data: dict) -> str:
        """新增关联信息记录，返回 record_id"""
        return self.bitable.write_record(USER_TABLES["related_info"], info_data)

    # ─── 用户查询 ────────────────────────────────────────────

    def get_all_users(self) -> list:
        """获取所有用户"""
        return self.bitable.query(USER_TABLES["users"])

    def get_user_by_name(self, user_name: str) -> dict:
        """按姓名查找用户"""
        users = self.bitable.query(
            USER_TABLES["users"],
            filter={"field_name": "姓名", "operator": "is", "value": [user_name]},
        )
        return users[0] if users else {}
