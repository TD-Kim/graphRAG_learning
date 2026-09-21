import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


# ============================================
# 1단계: Neo4j 연결
# ============================================
def create_neo4j_driver(uri, username, password):
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    try:
        driver.verify_connectivity()
        print(f"Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        raise
    
    return driver

def main():
    print("=" * 50)
    print("타이타닉 지식 그래프 추출")
    print("=" * 50)
    
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    
    if not NEO4J_PASSWORD:
        raise ValueError("NEO4J_PASSWORD 환경변수가 설정되지 않았습니다.")
    
    # 1. CSV 파일 경로 설정
    output_dir = Path("./output")
    csv_files = {
        "passenger": output_dir / "nodes_passenger.csv",
        "pclass": output_dir / "nodes_pclass.csv",
        "cabin": output_dir / "nodes_cabin.csv",
        "port": output_dir / "nodes_port.csv",
        "rel_pclass": output_dir / "rels_passenger_pclass.csv",
        "rel_cabin": output_dir / "rels_passenger_cabin.csv",
        "rel_port": output_dir / "rels_passenger_port.csv",
        "rel_traveled": output_dir / "rels_passenger_traveled.csv",
    }
    
    # 2. Neo4j 연결
    driver = create_neo4j_driver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    
if __name__ == "__main__":
    main()