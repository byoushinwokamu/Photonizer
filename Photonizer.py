import os
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import shutil

class ImageSorter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photonizer alpha")
        self.geometry("1200x800")
        
        self.target_folder = None
        self.target_keys = {}
        self.image_list = []
        self.current_image_index = 0
        self.last_moved_file = None
        
        self.load_targets()
        if not self.target_folder:
            messagebox.showerror("오류", "targets.txt 파일에서 원본 폴더를 찾을 수 없습니다.")
            self.destroy()
            return
            
        self.load_images()
        if not self.image_list:
            messagebox.showinfo("정보", f"'{self.target_folder}' 폴더에 이미지가 없습니다.")
            self.destroy()
            return

        self.create_widgets()
        self.show_image()

    def load_targets(self):
        """targets.txt 파일에서 폴더 및 단축키 정보를 불러옵니다."""
        try:
            with open("targets.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
                self.target_folder = lines[0].strip()
                for line in lines[1:]:
                    key, path = line.strip().split("=")
                    self.target_keys[key] = path
                    if not os.path.exists(path):
                        os.makedirs(path)
        except (FileNotFoundError, IndexError, ValueError):
            pass

    def load_images(self):
        """원본 폴더에서 이미지 파일을 불러옵니다."""
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        self.image_list = [
            f for f in os.listdir(self.target_folder)
            if os.path.isfile(os.path.join(self.target_folder, f)) and f.lower().endswith(valid_extensions)
        ]
        self.image_list.sort()

    def create_widgets(self):
        """GUI 위젯을 생성합니다."""
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 이미지 뷰어
        self.image_frame = tk.Frame(main_frame, width=800, height=600)
        self.image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))
        self.image_frame.pack_propagate(False)

        self.image_label = tk.Label(self.image_frame)
        self.image_label.pack(fill=tk.BOTH, expand=True)

        # 정보 표시 영역
        info_frame = tk.Frame(main_frame, width=300)
        info_frame.pack(side=tk.RIGHT, fill=tk.Y)

        current_file_label = tk.Label(info_frame, text="현재 파일:", font=("Arial", 12, "bold"))
        current_file_label.pack(anchor="w", pady=(0, 5))
        self.filename_label = tk.Label(info_frame, text="", font=("Arial", 10))
        self.filename_label.pack(anchor="w", pady=(0, 15))

        target_label = tk.Label(info_frame, text="타겟 폴더 (단축키):", font=("Arial", 12, "bold"))
        target_label.pack(anchor="w", pady=(0, 5))

        for key, path in self.target_keys.items():
            folder_name = os.path.basename(path)
            label_text = f"[{key}]  {folder_name}"
            label = tk.Label(info_frame, text=label_text, font=("Arial", 10))
            label.pack(anchor="w")

        # 키 바인딩
        for key in self.target_keys.keys():
            self.bind(f'<Key-{key}>', self.move_file)
        self.bind('<Key-z>', self.undo_move)

    def show_image(self):
        """현재 인덱스의 이미지를 화면에 표시합니다."""
        if self.current_image_index >= len(self.image_list):
            messagebox.showinfo("완료", "모든 이미지를 분류했습니다.")
            self.destroy()
            return
            
        file_name = self.image_list[self.current_image_index]
        file_path = os.path.join(self.target_folder, file_name)
        self.filename_label.config(text=file_name)
        
        try:
            image = Image.open(file_path)
            self.display_image(image)
        except Exception as e:
            messagebox.showerror("오류", f"이미지를 열 수 없습니다: {file_name}\n{e}")
            self.next_image()

    def display_image(self, image):
        """이미지를 창 크기에 맞춰 조정하고 표시합니다."""
        view_width = self.image_frame.winfo_width()
        view_height = self.image_frame.winfo_height()
        
        img_width, img_height = image.size
        
        # 비율 유지를 위한 크기 조정
        ratio_w = view_width / img_width
        ratio_h = view_height / img_height
        ratio = min(ratio_w, ratio_h)
        
        new_width = int(img_width * ratio)
        new_height = int(img_height * ratio)
        
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        self.photo = ImageTk.PhotoImage(resized_image)
        self.image_label.config(image=self.photo)
        
    def next_image(self):
        """다음 이미지로 넘어갑니다."""
        self.current_image_index += 1
        self.show_image()

    def move_file(self, event):
        """이미지를 선택된 폴더로 이동시킵니다."""
        key = event.keysym
        if key not in self.target_keys:
            return
            
        src_path = os.path.join(self.target_folder, self.image_list[self.current_image_index])
        dest_path = os.path.join(self.target_keys[key], self.image_list[self.current_image_index])
        
        try:
            shutil.move(src_path, dest_path)
            self.last_moved_file = (dest_path, src_path)
            self.image_list.pop(self.current_image_index)
            self.show_image()
        except Exception as e:
            messagebox.showerror("오류", f"파일 이동 실패: {e}")

    def undo_move(self, event):
        """마지막으로 이동한 파일을 원위치시킵니다."""
        if self.last_moved_file:
            src_path, dest_path = self.last_moved_file
            try:
                shutil.move(src_path, dest_path)
                messagebox.showinfo("실행 취소", "마지막 이동을 실행 취소했습니다.")
                
                # 원본 폴더로 돌아왔으므로 리스트에 다시 추가하고 인덱스 재설정
                self.load_images()
                self.current_image_index = self.image_list.index(os.path.basename(dest_path))
                self.show_image()
                self.last_moved_file = None
            except Exception as e:
                messagebox.showerror("오류", f"파일 복구 실패: {e}")
        else:
            messagebox.showinfo("정보", "실행 취소할 이동이 없습니다.")

if __name__ == "__main__":
    app = ImageSorter()
    app.mainloop()
