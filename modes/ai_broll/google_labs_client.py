import asyncio
import logging
import os
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext
from .account_pool_manager import Account

logger = logging.getLogger(__name__)

# URL giả định của Google Labs Flow/Whisk (tùy thuộc vào domain chính xác)
LABS_URL = "https://labs.google.com/video-fx" # Cần update đúng domain thực tế

class GoogleLabsError(Exception):
    pass

class GoogleLabsClient:
    def __init__(self, headless: bool = False):
        self.headless = headless
        # Chạy headed mode để dễ bề bypass CAPTCHA thủ công lần đầu

    async def _setup_context(self, p, account: Account) -> BrowserContext:
        """Tạo browser context và nhúng cookies."""
        browser = await p.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        if account.cookies:
            await context.add_cookies(account.cookies)
            
        return context

    async def _check_login(self, page: Page) -> bool:
        """Kiểm tra xem session có còn hiệu lực không."""
        # Giả lập check DOM element xác định avatar / login status
        try:
            # Wait for either avatar (logged in) or sign in button (logged out)
            login_indicator = await page.wait_for_selector(
                "div[aria-label='Google Account'], a[href*='ServiceLogin']", 
                timeout=10000
            )
            
            href = await login_indicator.get_attribute("href")
            if href and "ServiceLogin" in href:
                return False
            return True
        except Exception:
            return False

    async def generate_video_from_reference(
        self,
        account: Account,
        reference_image_path: str,
        prompt: str,
        mode: str = "image_to_video",
        output_dir: str = "temp/ai_broll/",
        timeout_sec: int = 180
    ) -> Optional[str]:
        """
        Sinh video thông qua automation Playwright.
        """
        os.makedirs(output_dir, exist_ok=True)
        
        async with async_playwright() as p:
            context = await self._setup_context(p, account)
            page = await context.new_page()
            
            try:
                logger.info(f"[LabsClient] Đang truy cập Google Labs với account {account.id}...")
                await page.goto(LABS_URL, timeout=30000)
                
                # 1. Kiểm tra session
                is_logged_in = await self._check_login(page)
                if not is_logged_in:
                    logger.error(f"[LabsClient] Account {account.id} cookie hết hạn hoặc bị văng login.")
                    raise GoogleLabsError("Session expired")

                # 2. Upload ảnh tham chiếu (Character/Product Consistency)
                if reference_image_path and os.path.exists(reference_image_path):
                    logger.info(f"[LabsClient] Uploading reference image: {reference_image_path}")
                    # Thay selector tương ứng với nút upload của Google Labs
                    # file_chooser = await page.wait_for_event("filechooser")
                    # await page.click("button[aria-label='Upload image']")
                    # await file_chooser.set_files(reference_image_path)
                    await asyncio.sleep(2) # Giả lập chờ upload xong

                # 3. Gõ prompt
                logger.info(f"[LabsClient] Gõ prompt: {prompt}")
                # await page.fill("textarea[aria-label='Prompt input']", prompt)
                
                # 4. Bấm Generate
                logger.info(f"[LabsClient] Bấm Generate & chờ render...")
                # await page.click("button:has-text('Generate')")

                # 5. Đợi render hoàn tất (thường mất 1-3 phút)
                # await page.wait_for_selector("video, .generation-result", timeout=timeout_sec * 1000)

                # 6. Lấy link video và tải về
                # video_src = await page.get_attribute("video", "src")
                # Xử lý download ...
                
                await asyncio.sleep(3) # Giả lập thời gian render (XÓA KHI CODE THẬT)
                
                # Dummy output
                fake_output_name = f"ai_broll_{account.id}_{abs(hash(prompt))}.mp4"
                fake_output_path = os.path.join(output_dir, fake_output_name)
                with open(fake_output_path, "wb") as f:
                    f.write(b"dummy video data")
                    
                logger.info(f"[LabsClient] Thành công! Đã lưu video: {fake_output_path}")
                return fake_output_path
                
            except Exception as e:
                logger.error(f"[LabsClient] Thất bại khi sinh video: {e}")
                return None
            finally:
                await context.close()
                await context.browser.close()
