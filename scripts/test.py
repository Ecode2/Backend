#! /bin/python3
import pdfplumber, sys, PyPDF2, fitz

def plumber_text_extract(pdf_path:str, page_num:int):
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        text += pdf.pages[page_num].extract_text()

    return text


def pypdf_text_extract(pdf_path:str, page_num:int):
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""

        page = reader.pages[page_num]
        text += page.extract_text()

    return text


def fitz_text_extract(pdf_path:str, page_num:int):
    document = fitz.open(pdf_path)
    text = ""
    page = document.load_page(page_num)
    text += page.get_text()
    return text


if __name__ == "__main__":
    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])

    print("plumber \n\n", plumber_text_extract(pdf_path, page_num), " \n\n")
    print("pypdf \n\n", pypdf_text_extract(pdf_path, page_num), " \n\n")
    print("fitz \n\n", fitz_text_extract(pdf_path, page_num), " \n\n")