import json
import logging
import os
import random
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict

logger = logging.getLogger(__name__)

# Quota an toàn cho mỗi tài khoản Google Labs (Flow/Whisk) mỗi ngày để tránh bị ban
DAILY_QUOTA_PER_ACCOUNT = 50

@dataclass
class Account:
    id: str
    cookies: List[Dict] = field(default_factory=list)
    email: str = ""
    is_active: bool = True

class AllAccountsExhaustedError(Exception):
    pass

class AccountPool:
    def __init__(self, config_path: str = "config/ai_broll_accounts.json"):
        self.config_path = config_path
        self.accounts: List[Account] = []
        self.usage_tracker: Dict[str, dict] = {}
        self._load_accounts()

    def _load_accounts(self):
        """Đọc danh sách tài khoản từ file JSON."""
        if not os.path.exists(self.config_path):
            logger.warning(f"[AccountPool] Không tìm thấy {self.config_path}. Dùng chế độ giả lập (Dummy).")
            # Tạo dummy accounts để test
            self.accounts = [
                Account(id="acc_dummy_1", email="dummy1@gmail.com"),
                Account(id="acc_dummy_2", email="dummy2@gmail.com")
            ]
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for acc_data in data.get("accounts", []):
                        self.accounts.append(
                            Account(
                                id=acc_data.get("id"),
                                cookies=acc_data.get("cookies", []),
                                email=acc_data.get("email", ""),
                                is_active=acc_data.get("is_active", True)
                            )
                        )
            except Exception as e:
                logger.error(f"[AccountPool] Lỗi đọc cấu hình: {e}")

        # Khởi tạo tracker
        today = datetime.now().strftime("%Y-%m-%d")
        for acc in self.accounts:
            self.usage_tracker[acc.id] = {
                "generations_today": 0,
                "last_reset": today
            }

    def _reset_quota_if_needed(self, acc_id: str):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.usage_tracker[acc_id]["last_reset"] != today:
            self.usage_tracker[acc_id]["generations_today"] = 0
            self.usage_tracker[acc_id]["last_reset"] = today

    def _is_quota_exhausted(self, acc: Account) -> bool:
        if not acc.is_active:
            return True
        self._reset_quota_if_needed(acc.id)
        return self.usage_tracker[acc.id]["generations_today"] >= DAILY_QUOTA_PER_ACCOUNT

    def get_available_account(self) -> Account:
        """Lấy tài khoản rảnh rỗi nhất (ít request trong ngày nhất)."""
        valid_accounts = [acc for acc in self.accounts if not self._is_quota_exhausted(acc)]
        
        if not valid_accounts:
            raise AllAccountsExhaustedError("Tất cả tài khoản Google Labs đều đã hết quota hoặc bị khóa.")
        
        # Sort ưu tiên account tạo ít video nhất
        valid_accounts.sort(key=lambda a: self.usage_tracker[a.id]["generations_today"])
        
        chosen = valid_accounts[0]
        # Randomize nhẹ nếu có nhiều account cùng mức usage (0)
        zeros = [a for a in valid_accounts if self.usage_tracker[a.id]["generations_today"] == self.usage_tracker[chosen.id]["generations_today"]]
        if len(zeros) > 1:
            chosen = random.choice(zeros)
            
        return chosen

    def mark_used(self, acc: Account):
        """Ghi nhận 1 lần tạo video thành công."""
        self._reset_quota_if_needed(acc.id)
        self.usage_tracker[acc.id]["generations_today"] += 1
        logger.debug(f"[AccountPool] Tài khoản {acc.email or acc.id} vừa dùng. Quota: {self.usage_tracker[acc.id]['generations_today']}/{DAILY_QUOTA_PER_ACCOUNT}")

    def report_banned(self, acc: Account):
        """Vô hiệu hóa account nếu phát hiện bị khóa hoặc đòi xác minh sđt."""
        logger.error(f"[AccountPool] CẢNH BÁO: Tài khoản {acc.id} bị khóa/ban!")
        acc.is_active = False

    def refresh_session(self, acc: Account):
        """
        Làm mới session. 
        Trong thực tế, Google bắt buộc refresh token/cookies thường xuyên.
        """
        logger.info(f"[AccountPool] Đang làm mới session cho {acc.email or acc.id}...")
        # TODO: Cắm logic Puppeteer/Playwright để thao tác login/refresh token nếu cần.
        pass

# Khởi tạo global instance (lazy load trong thực tế)
account_pool = None

def get_account_pool(config_path: str = "config/ai_broll_accounts.json") -> AccountPool:
    global account_pool
    if account_pool is None:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        account_pool = AccountPool(config_path)
    return account_pool
