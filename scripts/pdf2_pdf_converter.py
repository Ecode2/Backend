""" """ #! /usr/bin/python3
import fitz
from PIL import Image
from PyPDF2 import PdfReader

class PdfExtractor:

    def __init__(self, pdf_path:str, password: str = None):

        self.pdf_path = pdf_path
        self.password = password
        self.file_loader = self.load_pdf()
        self.reader: PdfReader = next(self.file_loader)
        

    def load_pdf(self):

        pdf_file = open(self.pdf_path, "rb")

        try:

            reader = PdfReader(pdf_file)

            if reader.is_encrypted and not self.password:
                raise ValueError("PDF encrypted and no password provided")

            elif reader.is_encrypted and self.password:
                if not reader.decrypt(self.password):
                    raise ValueError("Incorrect password for pdf decryption")
                
            yield reader

        except Exception as e:
            pdf_file.close()
            return e
                
        finally:
            pdf_file.close() 


    def get_total_page_number(self) -> int:
        if self.reader:
            return len(self.reader.pages)
        return 0
    
    def get_fist_page_image(self):
        
        #Returns a Pillow Image format
        
        if not self.reader:
            raise ValueError("PDF not loaded")
        
        pdf_file = fitz.open(self.pdf_path)

        first_page = pdf_file.load_page(0)
        pix = first_page.get_pixmap()

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        return img

    def get_one_page(self, page_number: int, total_page_number: int = None) -> str | IndexError:

        total_pages = total_page_number or self.get_total_page_number()

        if self.reader and 0 < page_number <= total_pages:

            page = self.reader.pages[page_number]
            return page.extract_text()
        
        raise IndexError("Page Number out of Range")

    def get_all_pages(self):
        
        total_pages = self.get_total_page_number()
        book_content = {}

        if total_pages == 0:
            IndexError("Page Number out of Range")

        for page in range(1, total_pages):
            page_content = self.get_one_page(page, total_pages)

            book_content[page] = page_content

        return book_content

    def is_encrypted(self) -> bool:
        return self.reader.is_encrypted
    
    def __del__(self):
        try:
            next(self.file_loader)
        except StopIteration:
            pass


if __name__ == "__main__":
    extractor = PdfExtractor(
        pdf_path="/home/e_code/Documents/programming/Web Development/Full-stack WebDev/SafariPdfReader/Backend/06 Harry Potter and the Half-Blood Prince - J..pdf"
    )

    #extractor.load_pdf()
    print(type(extractor.reader))

    print(extractor.get_total_page_number())

    print(extractor.is_encrypted())

    print(extractor.get_one_page(2))

    #print(extractor.get_all_pages())

    print(extractor.get_fist_page_image())