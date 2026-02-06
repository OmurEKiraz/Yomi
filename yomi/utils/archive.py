import os
import shutil
import zipfile
import img2pdf
from PIL import Image
from .metadata import generate_comic_info_xml

def create_cbz_archive(source_folder: str, output_path: str, metadata: dict = None) -> bool:
    """
    Klasörü CBZ (ZIP) yapar ve opsiyonel metadata (ComicInfo.xml) ekler.
    """
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as cbz:
            # 1. Resimleri Ekle
            for root, dirs, files in os.walk(source_folder):
                for file in sorted(files): # Sıralama önemli!
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=source_folder)
                    cbz.write(file_path, arcname)
            
            # 2. Metadata XML Ekle
            if metadata:
                xml_str = generate_comic_info_xml(metadata)
                cbz.writestr("ComicInfo.xml", xml_str)
                
        return True
    except Exception as e:
        print(f"CBZ Error: {e}")
        return False

def create_pdf_document(source_folder: str, output_path: str) -> bool:
    """
    Klasördeki resimleri tek bir PDF yapar.
    """
    try:
        images = []
        # Dosyaları isme göre sırala (001.jpg, 002.jpg...)
        for root, _, files in os.walk(source_folder):
            for file in sorted(files):
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    img_path = os.path.join(root, file)
                    
                    # WebP formatını PDF sevmez, JPG'e çevirip ekleyelim
                    if file.lower().endswith(".webp"):
                        im = Image.open(img_path).convert("RGB")
                        new_path = os.path.splitext(img_path)[0] + ".jpg"
                        im.save(new_path, "JPEG")
                        images.append(new_path)
                        # Orijinal webp'yi silebiliriz veya tutabiliriz, burada siliyoruz
                        os.remove(img_path)
                    else:
                        images.append(img_path)
        
        if not images: return False
        
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(images))
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False