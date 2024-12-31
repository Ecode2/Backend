from PIL import Image
from PyPDF2 import PdfReader
from fitz import Document, open as FitzReader

class PdfExtractor:

    def __init__(self, pdf_path:str, password: str = None):

        self.pdf_path = pdf_path
        self.password = password
        self.file_loader = self.load_pdf()
        self.reader: Document = next(self.file_loader)
        

    def load_pdf(self):

        pdf_file = open(self.pdf_path, "rb")

        try:

            reader: Document = FitzReader(pdf_file)

            if reader.is_encrypted and not self.password:
                raise ValueError("PDF encrypted and no password provided")

            elif reader.is_encrypted and self.password:
                if not reader.decrypt(self.password):
                    raise ValueError("Incorrect password for pdf decryption")
                
            yield reader

        except Exception as e:
            reader.close()
            return e
                
        finally:
            reader.close() 


    def get_total_page_number(self) -> int:
        if self.reader:
            return len(self.reader)
        return 0
    
    def get_fist_page_image(self):
        
        #Returns a Pillow Image format
        
        if not self.reader:
            raise ValueError("PDF not loaded")
        
        pdf_file = self.reader

        first_page = pdf_file.load_page(0)
        pix = first_page.get_pixmap()

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        return img

    def get_one_page(self, page_number: int, total_page_number: int = None) -> str | IndexError:

        total_pages = total_page_number or self.get_total_page_number()

        if self.reader and 0 < page_number <= total_pages:

            page = self.reader.load_page(page_number-1)
            return page.get_text()
        
        raise IndexError("Page Number out of Range")

    def get_all_pages(self):
        
        total_pages = self.get_total_page_number()
        book_content = {}

        if total_pages == 0:
            IndexError("Page Number out of Range")

        for page in range(total_pages):
            page_content = self.get_one_page(page+1, total_pages)

            book_content[page+1] = page_content

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
        pdf_path="/home/e_code/Documents/programming/Web Development/Full-stack WebDev/SafariPdfReader/Backend/scripts/06_Harry_Potter_and_the_Half-Blood_Prince__VyNxWaH..pdf"
    )

    #extractor.load_pdf()
    print(type(extractor.reader))

    print(extractor.get_total_page_number())

    print(extractor.is_encrypted())

    print("\n\n", extractor.get_one_page(50), "\n\n")

    print(extractor.get_all_pages())

    print(extractor.get_fist_page_image())