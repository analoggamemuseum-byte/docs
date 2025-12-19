#!/usr/bin/env python3
"""
JSONLファイルを統合するスクリプト
- sourceフィールドからハイフンの前のIDを抽出
- 同じIDのリソースを統合
- CSVからinstanceIDを追加
"""

import json
import csv
import requests
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set
from urllib.parse import urlencode


def extract_id_from_source(source: str) -> str:
    """sourceフィールドからハイフンの前のIDを抽出"""
    if "-" in source:
        return source.split("-")[0]
    # ハイフンがない場合は拡張子を除いた部分を返す
    return Path(source).stem


def load_id_instance_mapping(sparql_endpoint: str) -> Dict[str, str]:
    """SPARQLエンドポイントからitemIDとinstanceIDのマッピングを取得"""
    sparql_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX madb: <https://mediaarts-db.bunka.go.jp/data/property#>
PREFIX ag: <https://www.analoggamemuseum.org/ontology/>
PREFIX o: <http://omeka.org/s/vocabs/o#>

SELECT ?itemID ?instanceID WHERE {
  ?item ag:identifier ?itemID .
  ?item ag:exemplarOf ?tabletopgames .
  ?tabletopgames o:id ?instanceID .
}
"""
    
    headers = {
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {'query': sparql_query}
    
    mapping = {}
    
    try:
        print(f"SPARQLエンドポイントからIDマッピングを取得中: {sparql_endpoint}")
        response = requests.post(
            sparql_endpoint,
            headers=headers,
            data=urlencode(data),
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        
        if 'results' in result and 'bindings' in result['results']:
            for binding in result['results']['bindings']:
                if 'itemID' in binding and 'instanceID' in binding:
                    item_id = binding['itemID'].get('value', '')
                    instance_id = binding['instanceID'].get('value', '')
                    if item_id and instance_id:
                        mapping[item_id] = instance_id
        
        print(f"IDマッピングを {len(mapping)} 件取得しました")
        return mapping
        
    except Exception as e:
        print(f"警告: SPARQLクエリの実行に失敗しました: {e}")
        print("IDマッピングを空で続行します")
        return {}


def merge_cleaned_texts(texts: List[str]) -> str:
    """複数のcleaned_textを統合（重複を避ける）"""
    # 空文字列を除外
    non_empty_texts = [t for t in texts if t.strip()]
    if not non_empty_texts:
        return ""
    
    # 重複を避けて結合
    seen = set()
    unique_texts = []
    for text in non_empty_texts:
        if text not in seen:
            seen.add(text)
            unique_texts.append(text)
    
    return "\n\n".join(unique_texts)


def merge_entities(entities_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """複数のentitiesリストを統合（typeごとに値を集約）"""
    # typeごとに値を集約
    entities_by_type: Dict[str, Set[str]] = defaultdict(set)
    all_entities = []
    
    for entities in entities_list:
        for entity in entities:
            entity_type = entity.get("type", "")
            entity_text = entity.get("text", "").strip()
            
            if entity_text:
                # 同じtypeとtextの組み合わせを避ける
                key = f"{entity_type}:{entity_text}"
                if key not in entities_by_type[entity_type]:
                    entities_by_type[entity_type].add(key)
                    all_entities.append(entity)
    
    return all_entities


def merge_sections(sections_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """複数のsectionsリストを統合（重複を避ける）"""
    seen = set()
    merged_sections = []
    
    for sections in sections_list:
        for section in sections:
            # sectionの内容で重複チェック
            section_key = json.dumps(section, sort_keys=True, ensure_ascii=False)
            if section_key not in seen:
                seen.add(section_key)
                merged_sections.append(section)
    
    return merged_sections


def get_existing_metadata_oids(sparql_endpoint: str) -> Set[str]:
    """
    SPARQLエンドポイントから、既に人間が作成したメタデータのoidを取得
    count(?o) >= 15 のoidを返す
    """
    sparql_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX madb: <https://mediaarts-db.bunka.go.jp/data/property#>
PREFIX ag: <https://www.analoggamemuseum.org/ontology/>
PREFIX o: <http://omeka.org/s/vocabs/o#>

SELECT ?ttg ?oid (COUNT(?o) AS ?count) WHERE {
  ?ttg a ag:TableTopGame ;
	o:id ?oid ;
  ?p ?o .
} 
GROUP BY ?ttg ?oid
HAVING (COUNT(?o) >= 15)
"""
    
    headers = {
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {'query': sparql_query}
    
    try:
        print(f"SPARQLエンドポイントにクエリを送信中: {sparql_endpoint}")
        response = requests.post(
            sparql_endpoint,
            headers=headers,
            data=urlencode(data),
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        oids = set()
        
        if 'results' in result and 'bindings' in result['results']:
            for binding in result['results']['bindings']:
                if 'oid' in binding and 'value' in binding['oid']:
                    oid = binding['oid']['value']
                    count = binding.get('count', {}).get('value', '0')
                    oids.add(oid)
                    print(f"  既存メタデータ発見: oid={oid}, count={count}")
        
        print(f"既存メタデータのoid数: {len(oids)}")
        return oids
        
    except Exception as e:
        print(f"警告: SPARQLクエリの実行に失敗しました: {e}")
        print("既存メタデータのチェックをスキップします")
        return set()


def integrate_jsonl(
    input_jsonl_path: str,
    output_jsonl_path: str,
    output_csv_path: str,
    sparql_endpoint: str = "https://dydra.com/fukudakz/agmsearchendpoint/sparql"
) -> None:
    """JSONLファイルを統合し、JSONLとCSVの両方を出力"""
    
    # 既存メタデータのoidを取得
    existing_oids = get_existing_metadata_oids(sparql_endpoint)
    
    # SPARQLからIDマッピングを取得
    id_to_instance = load_id_instance_mapping(sparql_endpoint)
    
    # IDごとにオブジェクトをグループ化
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    with open(input_jsonl_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                obj = json.loads(line)
                source = obj.get("source", "")
                if not source:
                    print(f"警告: 行 {line_no} にsourceがありません")
                    continue
                
                # IDを抽出
                obj_id = extract_id_from_source(source)
                grouped[obj_id].append(obj)
                
            except json.JSONDecodeError as e:
                print(f"警告: 行 {line_no} のJSON解析エラー: {e}")
                continue
    
    print(f"{len(grouped)} 個のユニークなIDが見つかりました")
    
    # 統合されたオブジェクトを作成
    integrated_objects = []
    
    for obj_id, objects in grouped.items():
        # cleaned_textを統合
        cleaned_texts = [obj.get("cleaned_text", "") for obj in objects]
        merged_cleaned_text = merge_cleaned_texts(cleaned_texts)
        
        # entitiesを統合
        entities_list = [obj.get("entities", []) for obj in objects]
        merged_entities = merge_entities(entities_list)
        
        # 統合されたオブジェクトを作成
        integrated_obj = {
            "id": obj_id,
            "cleaned_text": merged_cleaned_text,
            "entities": merged_entities
        }
        
        # instanceIDを追加（CSVに存在する場合）
        if obj_id in id_to_instance:
            integrated_obj["instanceID"] = id_to_instance[obj_id]
        else:
            print(f"警告: ID '{obj_id}' に対応するinstanceIDが見つかりませんでした")
        
        # 元のsource情報も保持（参考用）
        sources = [obj.get("source", "") for obj in objects]
        integrated_obj["sources"] = sources
        
        integrated_objects.append(integrated_obj)
    
    # 統合されたオブジェクトをJSONLとして保存
    with open(output_jsonl_path, "w", encoding="utf-8") as f:
        for obj in integrated_objects:
            # instanceIDが既存メタデータのoidと一致する場合はentitiesを除外
            instance_id = obj.get("instanceID", "")
            if instance_id and instance_id in existing_oids:
                # entitiesを除外したコピーを作成
                obj_copy = obj.copy()
                obj_copy["entities"] = []
                # ag:catalogingDataStatusは空にする（JSONLには含めない）
                f.write(json.dumps(obj_copy, ensure_ascii=False) + "\n")
            else:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    
    # sectionsのtype（CSVの列から除外する、大文字小文字を区別しない）
    section_types_lower = {
        "catchphrase", "instruction", "meta", "rights", "safety_warning",
        "components", "credit", "immersion"
    }
    
    # すべてのentity typeを収集（sectionsのtypeは除外）
    all_entity_types = set()
    for obj in integrated_objects:
        for entity in obj.get("entities", []):
            entity_type = entity.get("type", "")
            if entity_type and entity_type.lower() not in section_types_lower:
                all_entity_types.add(entity_type)
    
    # entity typeをソートして列順を固定
    entity_type_columns = sorted(all_entity_types)
    
    # 既存メタデータでentitiesを除外したオブジェクト数をカウント
    entities_excluded_count = 0
    
    # 統合されたオブジェクトをCSVとして保存（区切り文字: ,、多値結合: ||）
    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        # 基本フィールド + entity type列 + ag:catalogingDataStatus（最後の列）
        fieldnames = ["id", "instanceID", "cleaned_text", "sources"] + entity_type_columns + ["ag:catalogingDataStatus"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for obj in integrated_objects:
            instance_id = obj.get("instanceID", "")
            
            # instanceIDが既存メタデータのoidと一致する場合はentitiesとag:catalogingDataStatusを除外
            is_existing_metadata = instance_id and instance_id in existing_oids
            
            # 基本フィールド
            row = {
                "id": obj.get("id", ""),
                "instanceID": instance_id,
                "cleaned_text": obj.get("cleaned_text", ""),
                "sources": "||".join(obj.get("sources", [])),
                "ag:catalogingDataStatus": "" if is_existing_metadata else "収蔵品の写真を元にAIで自動生成した目録データです"
            }
            
            if is_existing_metadata:
                entities_excluded_count += 1
                print(f"entities除外: instanceID={instance_id} は既存メタデータのためentitiesを除外（cleaned_textは追加）")
                # entitiesの列は全て空にする
                for entity_type in entity_type_columns:
                    row[entity_type] = ""
            else:
                # entitiesをtypeごとにグループ化
                entities_by_type: Dict[str, List[str]] = defaultdict(list)
                for entity in obj.get("entities", []):
                    entity_type = entity.get("type", "")
                    entity_text = entity.get("text", "").strip()
                    if entity_type and entity_text:
                        # 重複を避ける
                        if entity_text not in entities_by_type[entity_type]:
                            entities_by_type[entity_type].append(entity_text)
                
                # 各entity typeの値を||で結合（スペースなし）
                for entity_type in entity_type_columns:
                    values = entities_by_type.get(entity_type, [])
                    row[entity_type] = "||".join(values) if values else ""
            
            writer.writerow(row)
        
        if entities_excluded_count > 0:
            print(f"既存メタデータのためentitiesを除外したオブジェクト数: {entities_excluded_count}")
    
    print(f"\n統合完了:")
    print(f"  入力: {input_jsonl_path}")
    print(f"  出力JSONL: {output_jsonl_path}")
    print(f"  出力CSV: {output_csv_path}")
    print(f"  統合されたオブジェクト数: {len(integrated_objects)}")
    
    # 統計情報
    with_instance_id = sum(1 for obj in integrated_objects if "instanceID" in obj)
    print(f"  instanceIDが設定されたオブジェクト数: {with_instance_id}")
    
    # CSVに出力されたオブジェクト数（全てのオブジェクトが出力される）
    print(f"  CSVに出力されたオブジェクト数: {len(integrated_objects)}")


if __name__ == "__main__":
    input_path = "output_cleaned_1212_valid.jsonl"
    output_jsonl_path = "cleaned_1212_integrated.jsonl"
    output_csv_path = "cleaned_1212_integrated.csv"
    sparql_endpoint = "https://dydra.com/fukudakz/agmsearchendpoint/sparql"
    
    integrate_jsonl(input_path, output_jsonl_path, output_csv_path, sparql_endpoint)

