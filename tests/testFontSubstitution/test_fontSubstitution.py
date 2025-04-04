# This test needs to be in its own directory, so it can have it's own cwew2pdf.ini.
# Also we can store the asset files here.

# Test the clipart rendering with passepartout frame recoloring

#if you run this file directly, it won't have access to parent folder, so add it to python path
import sys
sys.path.append('..')
sys.path.append('.')
from pathlib import Path
import os, os.path
from pikepdf import Pdf
from cewe2pdf import convertMcf

def tryToBuildBook(keepDoublePages, expectedPages):
    inFile = str(Path(Path.cwd(), 'tests', 'testFontSubstitution', 'testfontsubstitution.mcf'))
    outFile = str(Path(Path.cwd(), 'tests', 'testFontSubstitution', 'testfontsubstitution.mcf.pdf'))
    if os.path.exists(outFile) == True:
        os.remove(outFile)
    assert os.path.exists(outFile) == False
    convertMcf(inFile, keepDoublePages)
    assert Path(outFile).exists() == True

    #check the pdf contents
    # we could also test more sophisticated things, like colors or compare images.
    readPdf = Pdf.open(outFile)
    numPages =  len(readPdf.pages)
    assert numPages == expectedPages, f"Expected {expectedPages} pages, found {numPages}"

    #os.remove(outFile)
    return numPages

def test_testfontsubstitution():
    tryToBuildBook(False, 28)

if __name__ == '__main__':
    #only executed when this file is run directly.
    test_testfontsubstitution()
