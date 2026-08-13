import os
import logging
import sqlite3
import numpy as np
from typing import Union, List, Tuple, Dict
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy loading of heavy TF modules
_TF_LOADED = False
tf = None
ResNet50 = None
preprocess_input = None
image_module = None
cosine_similarity = None

def _init_tf():
    global _TF_LOADED, tf, ResNet50, preprocess_input, image_module, cosine_similarity
    if not _TF_LOADED:
        logger.info("[VisualSearch] Đang nạp TensorFlow & ResNet50 (mất vài giây)...")
        import tensorflow as tf_lib
        from tensorflow.keras.applications.resnet50 import ResNet50 as RN50, preprocess_input as ppi
        from tensorflow.keras.preprocessing import image as img_mod
        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        
        # Suppress TF logging
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        
        tf = tf_lib
        ResNet50 = RN50
        preprocess_input = ppi
        image_module = img_mod
        cosine_similarity = cos_sim
        _TF_LOADED = True

class VisualSearchEngine:
    def __init__(self, db_path: str = "assets/product_db/crops"):
        self.db_path = db_path
        self.sqlite_db = os.path.join(self.db_path, "products.sqlite")
        self.model = None
        self.feature_vectors = None
        self.image_paths = []
        os.makedirs(self.db_path, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self):
        """Khởi tạo SQLite Database lưu Metadata"""
        conn = sqlite3.connect(self.sqlite_db)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT,
                price TEXT,
                key_claims TEXT,
                image_path TEXT UNIQUE
            )
        ''')
        conn.commit()
        conn.close()

    def save_metadata(self, name: str, price: str, claims: list, image_path: str):
        """Lưu metadata vào SQLite"""
        claims_str = ", ".join(claims) if claims else ""
        try:
            conn = sqlite3.connect(self.sqlite_db)
            c = conn.cursor()
            # Dùng REPLACE để ghi đè nếu trùng image_path
            c.execute('''
                INSERT OR REPLACE INTO products (product_name, price, key_claims, image_path)
                VALUES (?, ?, ?, ?)
            ''', (name, price, claims_str, image_path))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[VisualSearch] Lỗi lưu SQLite: {e}")

    def get_metadata(self, image_path: str) -> Dict:
        """Lấy metadata từ SQLite dựa trên đường dẫn ảnh"""
        conn = sqlite3.connect(self.sqlite_db)
        c = conn.cursor()
        c.execute('SELECT product_name, price, key_claims FROM products WHERE image_path = ?', (image_path,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "product_name": row[0] or "Unknown",
                "price": row[1] or "",
                "key_claims": row[2] or ""
            }
        return {"product_name": "Unknown", "price": "", "key_claims": ""}

    def load_model(self):
        if self.model is None:
            _init_tf()
            self.model = ResNet50(weights='imagenet', include_top=False, pooling='avg')
            logger.info("[VisualSearch] Đã nạp model ResNet50 thành công.")

    def extract_features(self, image_path: Union[str, BytesIO, Image.Image]) -> Union[np.ndarray, None]:
        self.load_model()
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.convert('RGB').resize((224, 224))
            else:
                img = image_module.load_img(image_path, target_size=(224, 224))
                
            img_array = image_module.img_to_array(img)
            expanded_img_array = np.expand_dims(img_array, axis=0)
            preprocessed_img = preprocess_input(expanded_img_array)
            
            features = self.model.predict(preprocessed_img, verbose=0).flatten()
            tf.keras.backend.clear_session()
            return features
        except Exception as e:
            logger.error(f"[VisualSearch] Lỗi trích xuất features: {e}")
            return None

    def refresh_db_index(self):
        self.load_model()
        feature_list = []
        paths = []
        
        logger.info(f"[VisualSearch] Đang quét database {self.db_path}...")
        for img_name in os.listdir(self.db_path):
            if img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                path = os.path.join(self.db_path, img_name)
                features = self.extract_features(path)
                if features is not None:
                    feature_list.append(features)
                    paths.append(path)
                    
        if feature_list:
            self.feature_vectors = np.vstack(feature_list)
            self.image_paths = paths
            logger.info(f"[VisualSearch] Đã index {len(paths)} ảnh sản phẩm.")
        else:
            self.feature_vectors = np.array([])
            self.image_paths = []

    def find_similar_images(self, 
                            query_image: Union[str, BytesIO, Image.Image], 
                            threshold: float = 0.85, 
                            top_n: int = 5) -> List[Dict]:
        """
        Tìm kiếm ảnh giống nhất với query_image. 
        Trả về list các dict chứa: path, score, và metadata (name, price, claims).
        """
        if self.feature_vectors is None or len(self.image_paths) == 0:
            self.refresh_db_index()
            
        if len(self.image_paths) == 0:
            logger.warning("[VisualSearch] Database trống, không thể so sánh.")
            return []

        query_features = self.extract_features(query_image)
        if query_features is None:
            return []

        similarities = cosine_similarity([query_features], self.feature_vectors)[0]
        
        results = []
        for i, score in enumerate(similarities):
            if score >= threshold:
                img_path = self.image_paths[i]
                meta = self.get_metadata(img_path)
                results.append({
                    "path": img_path,
                    "score": float(score),
                    "product_name": meta["product_name"],
                    "price": meta["price"],
                    "key_claims": meta["key_claims"]
                })
                
        results = sorted(results, key=lambda x: x["score"], reverse=True)
        return results[:top_n]
