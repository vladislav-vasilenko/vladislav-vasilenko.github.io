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
        metadatas = [{
            "title": v["title"], 
            "company": v["company"], 
            "link": v["link"], 
            "pub_date": v.get("pub_date", "Неизвестно"),
            "sphere": v.get("sphere", "Unknown")
        } for v in vacancies]
        
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

    def search_similar_vacancies_multi_chunk(
        self,
        cv_chunks: List[str],
        top_k: int = 40,
        pooling: str = "min",
        per_chunk_k: int = None,
    ) -> List[Dict[str, Any]]:
        """Search by embedding each CV chunk separately, then pool distances per vacancy.

        `pooling="min"` surfaces vacancies matching any single chunk strongly
        (a resume with backend+NLP experience won't bury NLP vacancies just
        because most positions were backend). `pooling="mean"` rewards
        breadth across the whole CV.
        """
        if not cv_chunks:
            return []
        if per_chunk_k is None:
            # Fetch more per chunk so aggregated top_k has good coverage.
            per_chunk_k = max(top_k, 50)

        print(
            f"🔍 Multi-chunk поиск: {len(cv_chunks)} чанков CV, "
            f"top_k={top_k}, pooling={pooling}, per_chunk_k={per_chunk_k}"
        )
        vectors = self.embeddings.embed_documents(cv_chunks)
        res = self.collection.query(query_embeddings=vectors, n_results=per_chunk_k)

        if not res.get("ids"):
            return []

        # Aggregate: job_id -> list of distances (one per chunk that surfaced it)
        job_dists: Dict[str, List[float]] = {}
        job_payload: Dict[str, Dict[str, Any]] = {}

        for chunk_idx in range(len(cv_chunks)):
            ids = res["ids"][chunk_idx] if chunk_idx < len(res["ids"]) else []
            if not ids:
                continue
            docs = res["documents"][chunk_idx]
            metas = res["metadatas"][chunk_idx]
            dists = res["distances"][chunk_idx]
            for j, jid in enumerate(ids):
                job_dists.setdefault(jid, []).append(float(dists[j]))
                if jid not in job_payload:
                    job_payload[jid] = {
                        "id": jid,
                        "document": docs[j],
                        "metadata": metas[j],
                    }

        pooled = []
        for jid, dlist in job_dists.items():
            if pooling == "min":
                score = min(dlist)
            elif pooling == "mean":
                score = sum(dlist) / len(dlist)
            else:
                raise ValueError(f"unknown pooling '{pooling}' (use 'min' or 'mean')")
            p = dict(job_payload[jid])
            p["distance"] = score
            p["matched_chunks"] = len(dlist)
            pooled.append(p)

        pooled.sort(key=lambda x: x["distance"])
        return pooled[:top_k]

    def get_all_ids(self) -> set:
        """Возвращает множество всех ID вакансий, хранящихся в базе."""
        try:
            res = self.collection.get(include=[])
            return set(res.get("ids", []))
        except Exception as e:
            print(f"⚠️ Ошибка при получении ID из базы: {e}")
            return set()

    def export_3d_embeddings(self, cv_text: str, ats_scores: Dict[str, int] = None, bt_statuses: Dict[str, bool] = None, foreign_statuses: Dict[str, bool] = None) -> List[Dict[str, Any]]:
        print("🌀 Запуск PCA для экспорта 3D пространства эмбеддингов...")
        if ats_scores is None:
            ats_scores = {}
        if bt_statuses is None:
            bt_statuses = {}
        if foreign_statuses is None:
            foreign_statuses = {}
            
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
                "is_big_tech": False,
                "is_foreign": False,
                "x": float(pca_result[0][0]),
                "y": float(pca_result[0][1]),
                "z": float(pca_result[0][2]),
                "ats_score": 100
            })
            
            # Vacancy Points (Index 1 to N)
            for idx, vec3d in enumerate(pca_result[1:]):
                job_id = db_ids[idx]
                scatter_data.append({
                    "id": job_id,
                    "title": db_metadatas[idx].get("title", "Unknown"),
                    "company": db_metadatas[idx].get("company", "Unknown"),
                    "link": db_metadatas[idx].get("link", "#"),
                    "sphere": db_metadatas[idx].get("sphere", "Other"),
                    "ats_score": ats_scores.get(job_id, 0),
                    "is_big_tech": bt_statuses.get(job_id, False),
                    "is_foreign": foreign_statuses.get(job_id, False),
                    "is_cv": False,
                    "x": float(vec3d[0]),
                    "y": float(vec3d[1]),
                    "z": float(vec3d[2])
                })
                
            return scatter_data
            
        except Exception as e:
            print(f"❌ Ошибка вычисления PCA 3D: {e}")
            return []
