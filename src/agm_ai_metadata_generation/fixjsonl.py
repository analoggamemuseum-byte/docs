# Gemini生成のjsonlファイルを有効なjsonlファイルに変換するスクリプト

import json
from pathlib import Path

def make_valid_jsonl(
    input_path: str,
    output_path: str,
    encoding: str = "utf-8",
) -> None:
    in_path = Path(input_path)
    out_path = Path(output_path)

    valid = 0
    invalid = 0

    with in_path.open("r", encoding=encoding) as fin, \
         out_path.open("w", encoding=encoding) as fout:

        for line_no, line in enumerate(fin, start=1):
            text = line.strip()
            if not text:
                continue  # 空行スキップ

            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                invalid += 1
                # 問題のある行番号を見たい場合はコメントアウトを外す
                # print(f"Invalid JSON at line {line_no}")
                continue

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            valid += 1

    print(f"Valid lines : {valid}")
    print(f"Invalid lines: {invalid}")


if __name__ == "__main__":
    # 必要であれば絶対パスに書き換えてください
    input_path = "/Users/fukudakazufumi/Library/CloudStorage/OneDrive-学校法人立命館/Codes/agm_image/output_cleaned_1212.jsonl"
    output_path = "/Users/fukudakazufumi/Library/CloudStorage/OneDrive-学校法人立命館/Codes/agm_image/output_cleaned_1212_valid.jsonl"

    make_valid_jsonl(input_path, output_path)