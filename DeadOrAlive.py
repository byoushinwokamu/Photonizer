import os
import sys

def save_path_info(path: str):
    # 파일명 추출 (예: dcinside0.txt)
    base_name = os.path.basename(path)
    txt_filename = f"{base_name}.txt"
    
    # 저장할 내용 구성
    content = (
        f"{path}\n"
        f"a={path}_alive\n"
        f"d={path}_dead\n"
    )
    
    # 파일 쓰기
    with open(txt_filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"저장 완료: {txt_filename}")

if __name__ == "__main__":
    # stdin으로 입력 받음
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        save_path_info(line)
