# AGM AI Metadata Generation

アナログゲームミュージアムの画像からメタデータを生成するためのツールセットです。

## 概要

このディレクトリには、ゲームパッケージ画像からOCRでテキストを抽出し、AI（Gemini）を使ってセクション分類と固有表現抽出を行い、最終的に統合されたメタデータを生成する一連のスクリプトが含まれています。

## ファイル構成

### 1. `googledocs_ocr.py`
**目的**: Google Driveに保存されたJPEG画像からOCRでテキストを抽出

**機能**:
- Google Drive APIを使用してフォルダ内のJPEG画像を取得（ページネーション対応）
- 画像をGoogleドキュメントに変換してOCRを実行
- 抽出されたテキストをJSONL形式で出力（`output.jsonl`）
- 6MB以上の画像は自動的に圧縮（最大2048x2048、JPEG品質85%）
- ファイルサイズの事前チェックとエラーハンドリング
- API制限を考慮した適切な間隔で処理（0.1秒間隔）

**使用方法**:
```bash
python googledocs_ocr.py
```

**必要な認証情報**:
- `credentials.json`: Google OAuth2認証情報
- `token.json`: 認証トークン（自動生成）

**出力**:
- `output.jsonl`: 各画像のファイル名（`image_filename`）と抽出テキスト（`extracted_text`）を含むJSONLファイル
- エラーが発生した画像については、エラーメッセージが`extracted_text`に記録されます

---

### 2. `gemini_process.sh`
**目的**: Gemini APIを使用してセクション分類と固有表現抽出を実行

**機能**:
- JSONLファイルをバッチ処理（デフォルト5行ずつ）
- 進捗管理機能（中断時も再開可能、`.gemini_progress`ファイルに保存）
- Gemini APIの出力からJSONのみを抽出（```jsonブロックまたはJSONオブジェクト形式に対応）
- 重複排除処理
- 完了時に進捗ファイルを自動削除

**使用方法**:
```bash
# 最初から処理
./gemini_process.sh

# 指定行から処理（例: 100行目から）
./gemini_process.sh 100

# 前回の続きから処理（進捗ファイルが存在する場合）
./gemini_process.sh
```

**設定変数**:
- `INPUT_FILE`: 入力JSONLファイル（デフォルト: `output_cleaned.jsonl`）
- `PROMPT_FILE`: Gemini API用のプロンプトファイル（`prompt_for_cli.txt`）
- `BATCH_SIZE`: バッチサイズ（デフォルト: 5）
- `OUTPUT_FILE`: 出力ファイル（デフォルト: `output_cleaned_1212.jsonl`）

**必要なツール**:
- `gemini` CLIコマンド（Google Gemini APIクライアント）

**出力**:
- `output_cleaned_1212.jsonl`: セクション分類と固有表現抽出結果を含むJSONLファイル

---

### 3. `fixjsonl.py`
**目的**: Gemini生成のJSONLファイルを有効なJSONLファイルに変換

**機能**:
- 無効なJSON行をスキップ
- 有効なJSON行のみを出力
- 統計情報（有効/無効行数）を表示

**使用方法**:
```bash
python fixjsonl.py
```

**設定**:
- スクリプト内の`input_path`と`output_path`を編集して使用（デフォルトは絶対パスが設定されています）

**出力**:
- `output_cleaned_1212_valid.jsonl`: 有効なJSONのみを含むJSONLファイル

---

### 4. `integrate_jsonl.py`
**目的**: JSONLファイルを統合し、JSONLとCSVの両方を出力

**機能**:
- `source`フィールドからハイフンの前のIDを抽出（例: `A737-002.jpeg` → `A737`）
- 同じIDのリソースを統合
  - `cleaned_text`: 重複を避けて結合
  - `entities`: typeごとに値を集約
- SPARQLエンドポイントからIDとinstanceIDのマッピングを取得（優先）
- SPARQLが利用できない場合は、ローカルCSVファイル（`ref/oid_and_itemID.csv`）からフォールバック
- 既存メタデータのチェック（SPARQLから`count(?o) >= 15`のoidを取得）
- 既存メタデータがある場合、entitiesを除外して`cleaned_text`のみを追加
- entitiesの各typeをCSVの列として展開（列名は`COLUMN_NAME_MAPPING`でマッピング）
- sectionsのtype（Catchphrase, Instructionなど）はCSVの列から除外
- `ag:catalogingDataStatus`列を追加（既存メタデータの場合は空、新規の場合は説明文を設定）

**使用方法**:
```bash
python integrate_jsonl.py
```

**設定**:
- `input_path`: 入力JSONLファイル（デフォルト: `output_cleaned_1212_valid.jsonl`）
- `output_jsonl_path`: 出力JSONLファイル（デフォルト: `cleaned_1212_integrated.jsonl`）
- `output_csv_path`: 出力CSVファイル（デフォルト: `cleaned_1212_integrated.csv`）
- `sparql_endpoint`: SPARQLエンドポイントURL（デフォルト: `https://dydra.com/fukudakz/agmsearchendpoint/sparql`）
- フォールバック用CSV: `ref/oid_and_itemID.csv`（SPARQLが利用できない場合に使用）

**出力形式**:
- **JSONL**: 
  - `id`: 抽出されたID
  - `cleaned_text`: 統合されたテキスト
  - `entities`: 統合されたエンティティ（既存メタデータがある場合は空配列）
  - `instanceID`: SPARQLまたはCSVから取得したinstanceID（存在する場合）
  - `sources`: 元のソースファイル名のリスト

- **CSV**:
  - 基本列: `id`, `o:id`（instanceIDのマッピング後）, `ag:packageText`（cleaned_textのマッピング後）, `sources`
  - Entity type列: entitiesの各typeが列として展開（列名は`COLUMN_NAME_MAPPING`でマッピング、例: `ag:designer`, `ag:publisher`など）
  - 最後の列: `ag:catalogingDataStatus`（既存メタデータの場合は空、新規の場合は説明文）
  - 区切り文字: カンマ（`,`）
  - 引用符: 全てのフィールドを`QUOTE_ALL`で囲む
  - 多値結合: `||`（スペースなし）

**注意**:
- sectionsのtype（Catchphrase, Instruction, Meta, Rights, Safety_warning, Components, Credit, Immersion）はCSVの列から除外されます
- 既存メタデータ（`count(?o) >= 15`）がある場合、entitiesは除外され、`cleaned_text`のみが追加されます
- 列名は`COLUMN_NAME_MAPPING`に従ってマッピングされます（例: `instanceID` → `o:id`, `cleaned_text` → `ag:packageText`）

---

### 5. `ref/oid_and_itemID.csv`（オプション）
**目的**: IDとinstanceIDのマッピングファイル（SPARQLエンドポイントが利用できない場合のフォールバック用）

**形式**:
```csv
"id","instanceID"
"A737","3405"
"A738","3404"
...
```

**注意**:
- このファイルは`integrate_jsonl.py`でSPARQLエンドポイントが利用できない場合にのみ使用されます
- ファイルが存在しない場合でも、SPARQLが利用できれば処理は続行されます

---

## 処理フロー

```
1. googledocs_ocr.py
   ↓
   output.jsonl (OCR抽出テキスト)

2. gemini_process.sh
   ↓
   output_cleaned_1212.jsonl (セクション分類・固有表現抽出)

3. fixjsonl.py
   ↓
   output_cleaned_1212_valid.jsonl (有効なJSONのみ)

4. integrate_jsonl.py
   ↓
   cleaned_1212_integrated.jsonl (統合されたJSONL)
   cleaned_1212_integrated.csv (統合されたCSV)
```

## 依存関係

### Pythonパッケージ
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2
pip install google-api-python-client
pip install Pillow  # 画像圧縮用（googledocs_ocr.pyで使用、オプション）
pip install requests  # HTTPリクエスト用（integrate_jsonl.pyでSPARQLクエリに使用）
```

### 外部ツール
- `gemini` CLIコマンド（Google Gemini APIクライアント）

## 認証設定

### Google API認証
1. Google Cloud Consoleでプロジェクトを作成
2. Google Drive APIとGoogle Docs APIを有効化
3. OAuth2認証情報をダウンロードして`credentials.json`として保存
4. 初回実行時にブラウザで認証を行い、`token.json`が自動生成されます

### Gemini API認証
- `gemini` CLIコマンドの認証設定が必要です
- 詳細はGemini APIのドキュメントを参照してください

## 注意事項

- Google APIにはレート制限があります（Drive API: 1分間に1800回）
- 大きな画像ファイルは自動的に圧縮されますが、6MBを超える場合はスキップされる可能性があります
- `gemini_process.sh`は進捗管理機能があるため、中断しても再開できます（`.gemini_progress`ファイルに保存）
- CSV出力では、同一プロパティの複数値は`||`で結合されます（スペースなし）
- `integrate_jsonl.py`はSPARQLエンドポイントからIDマッピングと既存メタデータ情報を取得します
- SPARQLエンドポイントが利用できない場合、ローカルCSVファイル（`ref/oid_and_itemID.csv`）がフォールバックとして使用されます
- 既存メタデータがある場合（`count(?o) >= 15`）、entitiesは除外され、`cleaned_text`のみが追加されます
- `fixjsonl.py`のデフォルトパスは絶対パスが設定されているため、使用前に編集が必要です

## ライセンス

（プロジェクトのライセンスに従ってください）

