import os
import chromadb
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings
from typing import List, Dict, Any
from dotenv import load_dotenv
from sklearn.decomposition import PCA

load_dotenv()

class RAGDatabase:
    def __init__(self, db_path: str = "./chroma_db"):
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)
        
        # Initialize Local ChromaDB
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # We will use Local Ollama Embeddings
        self.embeddings = OllamaEmbeddings(model="embeddinggemma")
        self.collection_name = "vacancies"
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"} # Используем косинусное расстояние
        )

    def add_vacancies(self, vacancies: List[Dict[str, Any]]):
        if not vacancies:
            return
            
        print(f"📥 Добавление {len(vacancies)} вакансий в базу ChromaDB...")
        
        ids = [str(v["id"]) for v in vacancies]
        texts = [f"Title: {v['title']}\nCompany: {v['company']}\nDate: {v.get('pub_date', 'Неизвестно')}\n\nDescription:\n{v['description']}" for v in vacancies]
        metadatas = [{"title": v["title"], "company": v["company"], "link": v["link"], "pub_date": v.get("pub_date", "Неизвестно")} for v in vacancies]
        
        # Check existing ids to prevent duplicates
        existing_res = self.collection.get(ids=ids)
        existing_ids = set(existing_res["ids"])
        
        new_ids = []
        new_texts = []
        new_metadatas = []
        
        for i, vid in enumerate(ids):
            if vid not in existing_ids:
                new_ids.append(vid)
                new_texts.append(texts[i])
                new_metadatas.append(metadatas[i])
                
        if not new_ids:
            print("ℹ️ В базе нет новых вакансий для добавления.")
            return
            
        # Векторизация и сохранение в Langchain + Chroma
        # Важно: ChromaDB может использовать встроенный OpenAI embedding function, 
        # но мы вручную сделаем embeded через LangChain
        vectors = self.embeddings.embed_documents(new_texts)
        
        self.collection.add(
            ids=new_ids,
            embeddings=vectors,
            documents=new_texts,
            metadatas=new_metadatas
        )
        print(f"✅ Успешно добавлено {len(new_ids)} новых вакансий в БД.")

    def search_similar_vacancies(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        print(f"🔍 Векторный поиск топ-{top_k} подходящих вакансий...")
        query_vector = self.embeddings.embed_query(query_text)
        
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k
        )
        
        matched_jobs = []
        if not results["ids"] or not results["ids"][0]:
            return matched_jobs
            
        for i in range(len(results["ids"][0])):
            matched_jobs.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] # Cosine distance
            })
            
        return matched_jobs

    def export_3d_embeddings(self, cv_text: str) -> List[Dict[str, Any]]:
        print("🌀 Запуск PCA для экспорта 3D пространства эмбеддингов...")
        try:
            # Получаем все векторы из ChromaDB
            data = self.collection.get(include=["embeddings", "metadatas", "documents"])
            if not data or data.get("embeddings") is None or len(data["embeddings"]) == 0:
                return []
                
            db_vectors = data["embeddings"]
            db_metadatas = data["metadatas"]
            db_ids = data["ids"]
            
            # Векторизуем резюме
            cv_vector = self.embeddings.embed_query(cv_text)
            
            # Объединяем векторы: [CV] + [Database]
            all_vectors = [cv_vector] + db_vectors
            
            # Проверка, хватает ли данных для 3D
            if len(all_vectors) < 3:
                return []
                
            # Обучаем PCA и трансформируем векторы в 3 координаты
            pca = PCA(n_components=3)
            pca_result = pca.fit_transform(all_vectors)
            
            scatter_data = []
            
            # CV Point (Index 0)
            scatter_data.append({
                "id": "user-cv",
                "title": "ВАШЕ РЕЗЮМЕ",
                "company": "Вы",
                "is_cv": True,
                "x": float(pca_result[0][0]),
                "y": float(pca_result[0][1]),
                "z": float(pca_result[0][2]),
            })
            
            # Vacancy Points (Index 1 to N)
            for idx, vec3d in enumerate(pca_result[1:]):
                scatter_data.append({
                    "id": db_ids[idx],
                    "title": db_metadatas[idx].get("title", "Unknown"),
                    "company": db_metadatas[idx].get("company", "Unknown"),
                    "link": db_metadatas[idx].get("link", "#"),
                    "is_cv": False,
                    "x": float(vec3d[0]),
                    "y": float(vec3d[1]),
                    "z": float(vec3d[2])
                })
                
            return scatter_data
            
        except Exception as e:
            print(f"❌ Ошибка вычисления PCA 3D: {e}")
            return []
