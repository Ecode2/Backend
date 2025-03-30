from PIL import Image
from fitz import Document, open as FitzReader

class PdfExtractor:
    def __init__(self, pdf_path: str, password: str = None):
        self.pdf_path = pdf_path
        self.password = password
        self.reader = None
        self._load_pdf()

    def _load_pdf(self):
        """Load the PDF file and handle encryption."""
        try:
            with open(self.pdf_path, "rb") as pdf_file:
                reader = FitzReader(pdf_file)
                if reader.is_encrypted:
                    if not self.password or not reader.authenticate(self.password):
                        raise ValueError("PDF encrypted and incorrect or no password provided")
                self.reader = reader
        except Exception as e:
            raise ValueError(f"Failed to load PDF: {str(e)}")

    def get_total_page_number(self) -> int:
        """Return the total number of pages in the PDF."""
        return len(self.reader) if self.reader else 0

    def get_fist_page_image(self):
        """Return the first page as a Pillow Image."""
        if not self.reader:
            raise ValueError("PDF not loaded")
        first_page = self.reader.load_page(0)
        pix = first_page.get_pixmap()
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def get_one_page(self, page_number: int, total_page_number: int = None) -> str:
        """Return the text content of a specific page."""
        total_pages = total_page_number or self.get_total_page_number()
        if self.reader and 0 < page_number <= total_pages:
            page = self.reader.load_page(page_number - 1)
            return page.get_text()
        raise IndexError("Page number out of range")

    def get_all_pages(self):
        """Return a dictionary of all pages' text content."""
        total_pages = self.get_total_page_number()
        if total_pages == 0:
            raise IndexError("No pages available")
        return {page + 1: self.get_one_page(page + 1, total_pages) for page in range(total_pages)}

    def is_encrypted(self) -> bool:
        """Check if the PDF is encrypted."""
        return self.reader.is_encrypted if self.reader else False

    def __del__(self):
        """Ensure the reader is closed."""
        if self.reader:
            self.reader.close()