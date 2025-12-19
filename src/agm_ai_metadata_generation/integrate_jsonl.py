#!/usr/bin/env python3
"""
JSONLファイルを統合するスクリプト
- sourceフィールドからハイフンの前のIDを抽出
- 同じIDのリソースを統合
- CSVからinstanceIDを追加
"""

import json
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set


def extract_id_from_source(source: str) -> str:
    """sourceフィールドからハイフンの前のIDを抽出"""
    if "-" in source:
        return source.split("-")[0]
    # ハイフンがない場合は拡張子を除いた部分を返す
    return Path(source).stem


def load_csv_mapping(csv_path: str) -> Dict[str, str]:
    """CSVファイルからIDとinstanceIDのマッピングを読み込む"""
    mapping = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_val = row["id"].strip('"')
            instance_id = row["instanceID"].strip('"')
            mapping[id_val] = instance_id
    return mapping


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


def integrate_jsonl(
    input_jsonl_path: str,
    output_jsonl_path: str,
    output_csv_path: str,
    csv_path: str
) -> None:
    """JSONLファイルを統合し、JSONLとCSVの両方を出力"""
    
    # CSVマッピングを読み込む
    id_to_instance = load_csv_mapping(csv_path)
    print(f"CSVから {len(id_to_instance)} 件のマッピングを読み込みました")
    
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
    
    # 統合されたオブジェクトをCSVとして保存（区切り文字: ,、多値結合: ||）
    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        # 基本フィールド + entity type列
        fieldnames = ["id", "instanceID", "cleaned_text", "sources"] + entity_type_columns
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for obj in integrated_objects:
            # 基本フィールド
            row = {
                "id": obj.get("id", ""),
                "instanceID": obj.get("instanceID", ""),
                "cleaned_text": obj.get("cleaned_text", ""),
                "sources": "||".join(obj.get("sources", []))
            }
            
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
    
    print(f"\n統合完了:")
    print(f"  入力: {input_jsonl_path}")
    print(f"  出力JSONL: {output_jsonl_path}")
    print(f"  出力CSV: {output_csv_path}")
    print(f"  統合されたオブジェクト数: {len(integrated_objects)}")
    
    # 統計情報
    with_instance_id = sum(1 for obj in integrated_objects if "instanceID" in obj)
    print(f"  instanceIDが設定されたオブジェクト数: {with_instance_id}")


if __name__ == "__main__":
    input_path = "output_cleaned_1212_valid.jsonl"
    output_jsonl_path = "cleaned_1212_integrated.jsonl"
    output_csv_path = "cleaned_1212_integrated.csv"
    csv_path = "oid_and_itemID.csv"
    
    integrate_jsonl(input_path, output_jsonl_path, output_csv_path, csv_path)

