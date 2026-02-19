#!/usr/bin/env python3
"""
webpファイルのリストをCSVに出力するスクリプト
dummy, url, itemID, resourceID, dcterms:titleの5列で出力
"""

import csv
import requests
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlencode


def extract_item_id(filename: str) -> str:
    """ファイル名からitem_idを抽出（例: B97-001.webp → B97）"""
    if "-" in filename:
        return filename.split("-")[0]
    return ""


def query_sparql_for_resource_ids(sparql_endpoint: str) -> Dict[str, str]:
    """
    SPARQLクエリを実行してitemIDからresourceID（item_oID）へのマッピングを取得
    
    Args:
        sparql_endpoint: SPARQLエンドポイントのURL
        
    Returns:
        itemIDからresourceIDへのマッピング辞書
    """
    sparql_query = """
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ag: <https://www.analoggamemuseum.org/ontology/>
PREFIX o: <http://omeka.org/s/vocabs/o#>
select ?itemID ?item_oID ?instance_oID {
  ?s rdf:type ag:Item ;
     o:id ?item_oID ;
     ag:identifier ?itemID ;
     ag:exemplarOf ?instance .
  ?instance o:id ?instance_oID .
}
"""
    
    headers = {
        'Accept': 'application/sparql-results+json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {'query': sparql_query}
    mapping = {}
    
    try:
        print(f"SPARQLエンドポイントからresourceIDマッピングを取得中: {sparql_endpoint}")
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
                if 'itemID' in binding and 'item_oID' in binding:
                    item_id = binding['itemID'].get('value', '')
                    item_o_id = binding['item_oID'].get('value', '')
                    if item_id and item_o_id:
                        mapping[item_id] = item_o_id
        
        print(f"resourceIDマッピングを {len(mapping)} 件取得しました")
        return mapping
        
    except Exception as e:
        print(f"警告: SPARQLクエリの実行に失敗しました: {e}")
        print("resourceIDマッピングを空で続行します")
        return {}


def list_webp_files(input_dir: str, output_csv: str, sparql_endpoint: str) -> None:
    """
    webpファイルのリストをCSVに出力
    
    Args:
        input_dir: webpファイルが格納されているディレクトリ
        output_csv: 出力CSVファイルのパス
        sparql_endpoint: SPARQLエンドポイントのURL
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"エラー: ディレクトリが見つかりません: {input_dir}")
        return
    
    # SPARQLからresourceIDマッピングを取得
    resource_id_mapping = query_sparql_for_resource_ids(sparql_endpoint)
    
    # .webpファイルを取得（サブディレクトリは除外）
    webp_files = sorted([f for f in input_path.iterdir() if f.is_file() and f.suffix == ".webp"])
    
    if not webp_files:
        print(f"警告: .webpファイルが見つかりません: {input_dir}")
        return
    
    # CSVファイルに書き込み
    base_url = "https://analoggamemuseum.org/temp/"
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["dummy", "url", "itemID", "resourceID", "dcterms:title"], quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for webp_file in webp_files:
            filename = webp_file.name
            item_id = extract_item_id(filename)
            url = base_url + filename
            resource_id = resource_id_mapping.get(item_id, "")
            
            writer.writerow({
                "dummy": "",
                "url": url,
                "itemID": item_id,
                "resourceID": resource_id,
                "dcterms:title": filename
            })
    
    print(f"CSVファイルを出力しました: {output_csv}")
    print(f"  処理したファイル数: {len(webp_files)}")
    # resourceIDが設定されたファイル数を表示
    resource_id_count = sum(1 for f in webp_files if resource_id_mapping.get(extract_item_id(f.name), ""))
    print(f"  resourceIDが設定されたファイル数: {resource_id_count}")


if __name__ == "__main__":
    input_directory = "output_images_webp"
    output_csv_path = "webp_files_list.csv"
    sparql_endpoint = "https://dydra.com/fukudakz/agmsearchendpoint/sparql"
    
    list_webp_files(input_directory, output_csv_path, sparql_endpoint)
