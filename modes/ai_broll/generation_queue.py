import asyncio
import logging
from typing import List, Optional

from .account_pool_manager import get_account_pool, Account, AllAccountsExhaustedError
from .google_labs_client import GoogleLabsClient

logger = logging.getLogger(__name__)

class GenerationQueue:
    def __init__(self, max_concurrent: int = 3):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.account_pool = get_account_pool()
        self.client = GoogleLabsClient(headless=False)
        self.account_locks = {} # Khóa account để đảm bảo 1 account = 1 task tại một thời điểm

    def _get_lock(self, acc_id: str) -> asyncio.Lock:
        if acc_id not in self.account_locks:
            self.account_locks[acc_id] = asyncio.Lock()
        return self.account_locks[acc_id]

    async def add_task(self, prompt: str, reference_image: str) -> asyncio.Future:
        """Đẩy task vào queue, trả về một Future để await kết quả."""
        future = asyncio.get_event_loop().create_future()
        await self.queue.put((prompt, reference_image, future))
        return future

    async def _worker(self):
        while True:
            prompt, reference_image, future = await self.queue.get()
            
            try:
                # Tìm tài khoản đang rảnh rỗi và chưa bị khóa bởi task khác
                # Vòng lặp nhỏ để đợi account nếu tất cả đang busy
                account: Optional[Account] = None
                lock: Optional[asyncio.Lock] = None
                
                while True:
                    try:
                        account = self.account_pool.get_available_account()
                        lock = self._get_lock(account.id)
                        
                        # Thử lấy lock, nếu không lấy được (đang chạy) thì skip sang account khác (hoặc sleep)
                        if lock.locked():
                            await asyncio.sleep(1)
                            continue
                            
                        await lock.acquire()
                        break # Đã tìm được account và lock thành công
                        
                    except AllAccountsExhaustedError:
                        logger.warning("[GenerationQueue] Hết account quota/rảnh rỗi, đợi 10s...")
                        await asyncio.sleep(10)
                
                try:
                    logger.info(f"[GenerationQueue] Đang xử lý prompt '{prompt[:30]}...' với Account {account.id}")
                    
                    video_path = await self.client.generate_video_from_reference(
                        account=account,
                        reference_image_path=reference_image,
                        prompt=prompt
                    )
                    
                    if video_path:
                        self.account_pool.mark_used(account)
                        future.set_result(video_path)
                    else:
                        future.set_result(None)
                        
                except Exception as e:
                    logger.error(f"[GenerationQueue] Lỗi khi generate: {e}")
                    future.set_exception(e)
                finally:
                    lock.release()
                    
            finally:
                self.queue.task_done()

    async def run_batch(self, tasks_data: List[dict]) -> List[Optional[str]]:
        """
        Khởi chạy queue, nhét task vào và đợi tất cả hoàn thành.
        tasks_data format: [{"prompt": "...", "reference_image": "..."}]
        """
        workers = [asyncio.create_task(self._worker()) for _ in range(self.max_concurrent)]
        
        futures = []
        for data in tasks_data:
            future = await self.add_task(data["prompt"], data.get("reference_image", ""))
            futures.append(future)
            
        await self.queue.join()
        
        # Hủy workers
        for w in workers:
            w.cancel()
            
        results = []
        for f in futures:
            try:
                results.append(f.result())
            except Exception:
                results.append(None)
                
        return results

# Singleton Queue
global_generation_queue = GenerationQueue()

def generate_batch_async(tasks_data: List[dict]) -> List[Optional[str]]:
    """Hàm bọc (wrapper) để gọi từ code đồng bộ (sync) nếu cần."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(global_generation_queue.run_batch(tasks_data))
    finally:
        loop.close()
