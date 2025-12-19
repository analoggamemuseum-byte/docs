# Gemini APIを使ったセクション分類と固有表現抽出処理
#!/bin/bash

INPUT_FILE="output_cleaned.jsonl"
PROMPT_FILE="prompt_for_cli.txt"
BATCH_SIZE=5
OUTPUT_FILE="output_cleaned_1212.jsonl"
PROGRESS_FILE=".gemini_progress"

# コマンドライン引数からスタート行を取得（デフォルトは1）
START_FROM=${1:-1}

LINE_COUNT=$(wc -l < "$INPUT_FILE")

# 進捗ファイルが存在し、引数が指定されていない場合は前回の続きから開始
if [ -f "$PROGRESS_FILE" ] && [ $# -eq 0 ]; then
  LAST_PROCESSED=$(cat "$PROGRESS_FILE")
  START_FROM=$((LAST_PROCESSED + 1))
  echo "Resuming from line $START_FROM (last processed: $LAST_PROCESSED)"
elif [ $# -eq 1 ]; then
  echo "Starting from specified line: $START_FROM"
else
  echo "Starting from beginning"
fi

# 出力ファイルが存在しない場合は作成
if [ ! -f "$OUTPUT_FILE" ]; then
  touch "$OUTPUT_FILE"
  echo "Created output file: $OUTPUT_FILE"
fi

echo "Total lines to process: $LINE_COUNT"
echo "Batch size: $BATCH_SIZE"
echo "Progress will be saved to: $PROGRESS_FILE"

# バッチ処理のループ
for i in $(seq $START_FROM $BATCH_SIZE $LINE_COUNT); do
  START_LINE=$i
  END_LINE=$((i + BATCH_SIZE - 1))
  
  # 最後のバッチで行数を超えないように調整
  if [ $END_LINE -gt $LINE_COUNT ]; then
    END_LINE=$LINE_COUNT
  fi
  
  echo "Processing lines $START_LINE to $END_LINE... ($(date))"
  
  # 指定範囲の行を抽出
  CHUNK=$(sed -n "${START_LINE},${END_LINE}p" "$INPUT_FILE")
  
  # API呼び出し実行と後処理
  TEMP_OUTPUT=$(mktemp)
  if (cat "$PROMPT_FILE"; echo "$CHUNK") | gemini > "$TEMP_OUTPUT"; then
    # Gemini出力の後処理：JSONのみ抽出（重複回避）
    TEMP_JSON=$(mktemp)
    
    # 優先順位1: ```jsonブロック内を抽出
    if grep -q '^```json$' "$TEMP_OUTPUT"; then
      sed -n '/^```json$/,/^```$/p' "$TEMP_OUTPUT" | sed '/^```/d' | grep -v '^$' > "$TEMP_JSON"
    else
      # 優先順位2: JSONオブジェクト（{...}）を抽出
      awk '/^{/,/^}$/' "$TEMP_OUTPUT" | grep -v '^$' > "$TEMP_JSON"
    fi
    
    # 重複排除してメインファイルに追加
    if [ -s "$TEMP_JSON" ]; then
      sort -u "$TEMP_JSON" >> "$OUTPUT_FILE"
    fi
    rm "$TEMP_JSON"
    
    # 成功時：進捗を保存
    echo $END_LINE > "$PROGRESS_FILE"
    echo "✓ Processed lines $START_LINE-$END_LINE"
    rm "$TEMP_OUTPUT"
  else
    # 失敗時：エラーメッセージとともに停止
    echo "✗ Error processing lines $START_LINE-$END_LINE"
    echo "Resume with: $0 $START_LINE"
    rm "$TEMP_OUTPUT"
    exit 1
  fi
  
  # API負荷軽減のための待機
  sleep 1
  
  # 進捗表示
  PERCENT=$((END_LINE * 100 / LINE_COUNT))
  echo "Progress: $END_LINE/$LINE_COUNT ($PERCENT%)"
done

# 完了時の処理
echo "Processing complete! Results saved to $OUTPUT_FILE"
echo "Processed $LINE_COUNT lines in total."

# 完了時は進捗ファイルを削除
if [ -f "$PROGRESS_FILE" ]; then
  rm "$PROGRESS_FILE"
  echo "Progress file removed."
fi