import os
import json
import time
import io
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload
try:
    from PIL import Image
except ImportError:
    print("警告: PILライブラリがインストールされていません。画像圧縮機能は無効になります。")
    print("インストールするには: pip install Pillow")
    Image = None

# スコープの定義：Google DriveとGoogle Docsへのアクセス許可
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents.readonly'
]

def compress_image_if_needed(drive_service, image_id, image_name, file_size):
    """
    画像が大きすぎる場合に圧縮する関数
    """
    if not Image or file_size <= 6000000:  # PILが利用できない、または6MB以下の場合はそのまま返す
        return image_id, False
    
    try:
        print(f"画像を圧縮中: {image_name} ({file_size:,} bytes)")
        
        # 元の画像をダウンロード
        file_content = drive_service.files().get_media(fileId=image_id).execute()
        
        # PILで画像を開く
        image = Image.open(io.BytesIO(file_content))
        
        # 画像を適切なサイズに圧縮（品質とサイズのバランスを調整）
        max_size = (2048, 2048)  # 最大解像度
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # JPEG形式で圧縮（品質85%）
        compressed_buffer = io.BytesIO()
        if image.mode in ('RGBA', 'LA', 'P'):
            # 透明度がある場合は白背景に変換
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        
        image.save(compressed_buffer, format='JPEG', quality=85, optimize=True)
        compressed_buffer.seek(0)
        
        compressed_size = len(compressed_buffer.getvalue())
        print(f"圧縮完了: {file_size:,} bytes → {compressed_size:,} bytes")
        
        if compressed_size >= file_size * 0.9:  # 圧縮効果が少ない場合
            print("圧縮効果が少ないため、元のファイルを使用します")
            return image_id, False
        
        # 圧縮した画像を一時的にアップロード
        compressed_name = f"compressed_{image_name}"
        media = MediaIoBaseUpload(compressed_buffer, mimetype='image/jpeg')
        
        file_metadata = {'name': compressed_name}
        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        
        return uploaded_file.get('id'), True
        
    except Exception as e:
        print(f"画像圧縮エラー: {e} - 元のファイルを使用します")
        return image_id, False

def main():
    """
    Google DriveのJPEGからテキストを抽出しJSONLに出力するメイン関数
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        drive_service = build('drive', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)

        folder_id = input("Google DriveのフォルダIDを入力してください: ")
        if not folder_id.strip():
            print("\nエラー: フォルダIDが入力されていません。スクリプトを終了します。")
            return

        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/jpg')"
        
        # 全てのファイルを取得するためのページネーション処理
        items = []
        page_token = None
        
        while True:
            results = drive_service.files().list(
                q=query, 
                pageSize=100,  # 1回のリクエストで最大100件
                pageToken=page_token,
                fields="nextPageToken, files(id, name)"
            ).execute()
            
            current_items = results.get('files', [])
            items.extend(current_items)
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break  # 次のページがない場合は終了
            
            print(f"現在 {len(items)} 件のファイルを取得しました。続行中...")

        if not items:
            print("指定されたフォルダにJPEG画像が見つかりませんでした。")
            return

        print(f"{len(items)}個のJPEG画像が見つかりました。処理を開始します...")
        jsonl_data = []

        for index, item in enumerate(items, 1):
            image_name = item['name']
            image_id = item['id']
            print(f"処理中 ({index}/{len(items)}): {image_name}")

            # ★★★ 修正箇所 ★★★
            # ファイルサイズを事前にチェック
            try:
                # ファイルのメタデータを取得してサイズをチェック
                file_metadata = drive_service.files().get(
                    fileId=image_id, fields='size'
                ).execute()
                
                file_size = int(file_metadata.get('size', 0))
                print(f"ファイルサイズ: {file_size:,} bytes")
                
                # 画像圧縮を試行（必要に応じて）
                processing_image_id, is_compressed = compress_image_if_needed(
                    drive_service, image_id, image_name, file_size
                )
                
                # 圧縮後もサイズが大きすぎる場合はスキップ
                if is_compressed:
                    # 圧縮されたファイルのサイズを再チェック
                    compressed_metadata = drive_service.files().get(
                        fileId=processing_image_id, fields='size'
                    ).execute()
                    compressed_size = int(compressed_metadata.get('size', 0))
                    
                    if compressed_size > 6000000:
                        # 圧縮してもまだ大きすぎる場合
                        drive_service.files().delete(fileId=processing_image_id).execute()
                        skip_message = f"スキップ: 圧縮後もファイルサイズが大きすぎます ({compressed_size:,} bytes > 6MB制限)"
                        print(skip_message)
                        jsonl_data.append({
                            "image_filename": image_name,
                            "extracted_text": skip_message
                        })
                        continue
                elif file_size > 6000000:
                    # 圧縮できず、元のファイルが大きすぎる場合
                    skip_message = f"スキップ: ファイルサイズが大きすぎます ({file_size:,} bytes > 6MB制限)"
                    print(skip_message)
                    jsonl_data.append({
                        "image_filename": image_name,
                        "extracted_text": skip_message
                    })
                    continue
                
                print("処理を続行します")
                
            except Exception as e:
                print(f"ファイルサイズ取得エラー: {e} - 処理を続行します")
            
            # ファイルごとの処理をtry...exceptで囲み、エラーを捕捉する
            try:
                # 画像をGoogleドキュメントに変換（OCR実行）
                copy_request = {
                    'name': os.path.splitext(image_name)[0],
                    'mimeType': 'application/vnd.google-apps.document'
                }
                copied_file = drive_service.files().copy(
                    fileId=processing_image_id, body=copy_request).execute()
                doc_id = copied_file['id']

                # Googleドキュメントからテキストを抽出
                doc = docs_service.documents().get(documentId=doc_id).execute()
                doc_content = doc.get('body').get('content')
                
                text = ''
                if doc_content:
                    for value in doc_content:
                        if 'paragraph' in value:
                            elements = value.get('paragraph').get('elements')
                            for elem in elements:
                                if 'textRun' in elem:
                                    text += elem.get('textRun').get('content')
                
                jsonl_data.append({
                    "image_filename": image_name,
                    "extracted_text": text.strip()
                })
                
                # 一時的に作成したGoogleドキュメントを削除
                drive_service.files().delete(fileId=doc_id).execute()
                
                # 圧縮されたファイルがある場合は削除
                if is_compressed:
                    try:
                        drive_service.files().delete(fileId=processing_image_id).execute()
                    except Exception as e:
                        print(f"圧縮ファイル削除エラー: {e}")
                
                print(f"完了 ({index}/{len(items)}): {image_name} のテキストを抽出しました。")
                
                # API制限を考慮して適切な間隔を設ける（1分間に1800回制限 = 約0.033秒間隔）
                # 安全のため0.1秒間隔で処理
                time.sleep(0.1)

            except HttpError as error:
                # HttpErrorを捕捉し、特に413エラー(Request Too Large)の場合の処理を記述
                if error.resp.status == 413:
                    error_message = "エラー: ファイルが大きすぎるため処理できませんでした。"
                    print(error_message)
                    jsonl_data.append({
                        "image_filename": image_name,
                        "extracted_text": error_message
                    })
                else:
                    # その他のAPIエラー
                    error_message = f"エラー: APIエラーが発生しました。 {error}"
                    print(error_message)
                    jsonl_data.append({
                        "image_filename": image_name,
                        "extracted_text": error_message
                    })
            except Exception as e:
                # その他の一般的なエラー
                error_message = f"エラー: 予期せぬエラーが発生しました。 {e}"
                print(error_message)
                jsonl_data.append({
                    "image_filename": image_name,
                    "extracted_text": error_message
                })
            # ★★★ ここまで ★★★

        # JSONLファイルに出力
        with open('output.jsonl', 'w', encoding='utf-8') as jsonlfile:
            for data in jsonl_data:
                jsonlfile.write(json.dumps(data, ensure_ascii=False) + '\n')

        print(f"\n全ての処理が完了しました。")
        print(f"処理済みファイル数: {len(jsonl_data)}/{len(items)}")
        print(f"結果ファイル: 'output.jsonl'")

    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")

if __name__ == '__main__':
    main()