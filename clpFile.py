# SPDX-License-Identifier:LGPL-3.0-only or GPL-3.0-only

# Copyright (c) 2020 by BarchSteel

import logging
from pathlib import Path
from io import BytesIO
import re
import cairosvg
import PIL
from PIL import Image
# from PIL import ImageOps
# from PIL.ExifTags import TAGS

class ClpFile():
    _invalidContent = r"? illegal clp content"

    def __init__(self, clpFileName:str = ""):
        """Constructor with file name will open and read .CLP file"""
        self.svgData: bytes = bytes()   # the byte representation of the SVG file
        self.pngMemFile: BytesIO = BytesIO(bytes())     # this can be used to access the buffer like a file.

        if clpFileName:
            self.readClp(clpFileName)

    def readClp(self, fileName) -> None:
        """Read a .CLP file and convert it to a .SVG file.

         reads the data into the internal buffer as SVG

         Remarks: The current implementation using immutable strings may not be best.
           But it should work for typical cliparts with a size of less then a few megabytes."""

        inFilePath = Path(fileName)
        # self.nameSavedForDebugging = str(inFilePath)
        # open and read the whole file to memory
        contents = ClpFile._invalidContent
        with open(inFilePath, "rt") as fileClp: # pylint: disable=unspecified-encoding
            contents = fileClp.read()

        # check the header
        if contents[0] != 'a':
            raise ValueError(f"A .clp file should start with character 'a', but instead it was: {contents[0]} ({hex(ord(contents[0]))})")
        # start after the header and remove all invalid characters
        invalidChars = 'ghijklmnopqrstuvwxyz'
        hexData = contents[1:].translate({ord(i): None for i in invalidChars})

        # the string is hexadecimal representation of the real data. Let's convert it back.
        svgData = bytes.fromhex(hexData)
        self.svgData = svgData

    def saveToSVG(self, outfileName):
        """save internal SVG data to a file"""
        with open(outfileName, "wb") as outFile: # pylint: disable=unspecified-encoding
            outFile.write(self.svgData)

    def convertToPngInBuffer(self, width:int = None, height:int = None, alpha:int = 128, flipX = False, flipY = False): # noqa: E251
        """convert the SVG to a PNG file, but only in memory"""

        # create a byte buffer that can be used like a file and use it as the output of svg2png.
        scaledImage = self.rasterSvgData(width, height)

        if scaledImage.mode == "RGB":
            # create a mask the same size as the original. For all pixels which are
            # non zero ("not used") set the mask value to the required transparency
            # L = 8-bit gray-scale
            # Important: .convert('L') should not be used on RGBA images -> very bad quality. Not supported.
            alphamask = scaledImage.copy().convert('L').resize(scaledImage.size)
            pixels = alphamask.load()
            for i in range(alphamask.size[0]): # for every pixel:
                for j in range(alphamask.size[1]):
                    if (pixels[i, j] != 0):
                        pixels[i, j] = alpha
            scaledImage.putalpha(alphamask)

        if flipX:
            scaledImage = scaledImage.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flipY:
            scaledImage = scaledImage.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        scaledImage.save(self.pngMemFile, 'png')
        self.pngMemFile.seek(0)
        return self

    def rasterSvgData(self, width:int, height:int):

        # We are using cairosvg, but this does not allow to scale the output image to the dimensions that we like.
        # we need to do a two-pass convertion, to get the desired result
        # 1. Do the first conversion and see what the output size is
        # 2. calculate the scaling in x-, and y-direction that is needed
        # 3. use the maxium of these x-, and y-scaling and do a aspect-ratio-preserving scaling of the image
        #    convert the image again from svg to png with this max. scale factor
        # 4. do a raster-image scaling to skew the image to the final dimension.
        #    This should only scale in x- or y-direction, as the other direction should alread be the desired one.

        # create a byte buffer that can be used like a file and use it as the output of svg2png.
        tmpMemFile = BytesIO()
        # Step 1.
        cairosvg.svg2png(bytestring=self.svgData, write_to=tmpMemFile, unsafe=True)
        tmpMemFile.seek(0)
        tempImage = PIL.Image.open(tmpMemFile)
        origWidth = tempImage.width
        origHeight = tempImage.height
        # Step 2.
        scale_x = width/origWidth
        scale_y = height/origHeight
        # Step 3.
        scaleMax = max(scale_x, scale_y)
        tmpMemFile = BytesIO()
        cairosvg.svg2png(bytestring=self.svgData, write_to=tmpMemFile, scale=scaleMax, unsafe=True)
        # Step 4.
        tmpMemFile.seek(0)
        tempImage = PIL.Image.open(tmpMemFile)
        scaledImage = tempImage.resize((width, height))
        return scaledImage

    # def convertMaskToPngInBuffer(self, width:int = None, height:int = None):
    #     """convert a loaded mask (.clp, .SVG) to a in-memory PNG file
    #         Use this for the passepartout frames.
    #      """

    #     #create a byte buffer that can be used like a file and use it as the output of svg2png.
    #     maskImgPng:PIL.Image = self.rasterSvgData(width, height)

    #     maskImgPng.save(self.pngMemFile, 'png')
    #     self.pngMemFile.seek(0)
    #     return self

    def applyAsAlphaMaskToFoto(self, photo:PIL.Image):
        """" Use the currently loaded mask clipart to create a alpha mask on the input image."""
        # create the PNG as RBGA in internal buffer
        # create a byte buffer that can be used like a file and use it as the output of svg2png.
        maskImgPng:PIL.Image = self.rasterSvgData(photo.width, photo.height)

        # get the alpha channel
        #  if the .svg is fully filled by the mask, then only a black rectangle with RGA (=no background!) is returned.
        #  if the mask does not fully fill the mask, then an RGBA image is returned. In this case, use the alpha value directly.
        if maskImgPng.mode == "RGBA":
            # an RGBA image mask does not always use transparency
            # some images still use white to indicate transparent parts
            # to support both transparent and white RGBA svg masks,
            # convert transparency to white and use white as alpha channel.
            #  alphaChannel = maskImgPng.getchannel("A")
            #  maskImgPng.paste("white", None, "RGBA")

            white = PIL.Image.new("RGBA", maskImgPng.size, "WHITE")
            white.paste(maskImgPng, (0, 0), maskImgPng)
            alphaChannel = white.convert('L')
            alphaChannel = PIL.ImageOps.invert(alphaChannel)
        elif maskImgPng.mode == "RGB":
            # convert image to gray-scale and use that as alpha channel.
            # we need to invert, otherwise black whould be transparent.
            # normally the whole image is a black rectangle
            alphaChannel = maskImgPng.convert('L')
            alphaChannel = PIL.ImageOps.invert(alphaChannel)

        # apply it the input photo. They must have the same dimensions. But that is ensured by rasterSvgData
        if (photo.mode != "RGB") or (photo.mode != "RGBA"):
            photo = photo.convert("RGBA")
        photo.putalpha(alphaChannel)

        return photo

    def savePNGfromBufferToFile(self, fileName) -> None:
        """ write the internal PNG buffer to a file """
        with open(fileName,"wb") as outFile:
            outFile.write(self.pngMemFile.read())
        self.pngMemFile.seek(0) # reset file pointer back to the start for other function calls

    def loadFromSVG(self, inputFileSVG:str):
        # read SVG file into memory
        with open(inputFileSVG,"rb") as svgFile: # input file should be UTF-8 encoded, but we read in binary mode
            self.svgData = svgFile.read()
        return self

    def replaceColors(self, colorReplacementList):
        """ Replace colors in the clipart

        This does a simple text replacement of color strings in the clipart.

        colorReplacementList: list of tuples
            first element of tuple: original color
            second element: new color

        The color must be a string, and it must be exactly as it appears in the .SVG file as text.
        """

        if len(colorReplacementList) < 1:
            return self

        # the colors are in the form of: style="fill:#112233"
        #   or style="opacity:0.40;fill:#112233",
        #   or style="stroke:#112233"
        #   and potentially mixed in with the other keywords which are possible in the style spec

        # In the investigation of issue https://github.com/bash0/cewe2pdf/issues/85 I found a clipart (1134365)
        # which has no <g> grouping element surrounding the <path>, and thus no fill or stroke style attributes
        # in the grouping, which is where cewe seem to put these. In this case everything in the svg is
        # rendered in black, so we need only to check if there is requested replacement for black and if
        # so we add in a stroke defintion for the new color. We could add fill too, but that seems a bit odd.
        # I observe (https://www.geeksforgeeks.org/svg-path-element/) that it is possible to use fill and
        # stroke in the path itself, so my hack for #85 is to add to the path itself if neither is present
        # anywhere in the svgdata
        svgDataText = self.svgData.decode()
        if ("fill" not in svgDataText) and ("stroke" not in svgDataText):
            for curReplacement in colorReplacementList:
                if curReplacement[0] == "#000000":
                    replacement = svgDataText.replace('<path ', f'<path fill="{curReplacement[1]}" stroke="{curReplacement[1]}" ')
                    self.svgData = replacement.encode(encoding="utf-8")
                    return self
        # More issue #85 stuff. This is for clipart 129188, 14466-CLIP-EMBOSS-GD.xml and similar.
        # It's a hollow figure with no fill and a black rectangular frame. This will hopefully fix
        # a more general case of an unfilled frame with a color replacement for the frame
        if ('fill="none"' in svgDataText) and ("stroke" not in svgDataText):
            for curReplacement in colorReplacementList:
                if curReplacement[0] == "#000000":
                    replacement = svgDataText.replace('fill="none"', f'fill="none" stroke="{curReplacement[1]}" ')
                    self.svgData = replacement.encode(encoding="utf-8")
                    return self
        # As long as we continue to make assumptions that the cliparts are so simple that we
        # can textually find and replace fill and stroke, then we're surely going to find more
        # cliparts that we don't recolour properly, in particular when recolouring black which
        # seems to be specified by the *absence* of the colour keyword.
        # But parsing svg is a much bigger job!

        for curReplacement in colorReplacementList:
            if curReplacement[0] == curReplacement[1]:
                # color was not changed
                continue

            # print (curReplacement)
            # Old, simple, but buggy code: self.svgData = self.svgData.replace(oldColorString.encode(encoding="utf-8"),newColorString.encode(encoding="utf-8") )
            # A general replace would look like this:
            #     re.sub("(style=\".*?)(fill:\#[0-9a-fA-F]+)(.*?\")", r"\1"+XXX+r"\3", self.svgData)
            # This does the replacements "fairly carefully" for both fill and stroke. As an attempt
            # at a "sanity" check we insist that each color replacement should be used at least once
            subsmade = 0
            colorkeys = ("fill", "stop-color", "stroke")
            for colorkey in colorkeys:
                oldColorString = colorkey+':'+curReplacement[0]
                newColorString = colorkey+':'+curReplacement[1]
                replacement, subcount = re.subn(
                    "(style=\".*?)("+oldColorString+")(.*?\")", r"\1"+newColorString+r"\3", self.svgData.decode(),flags=re.MULTILINE | re.IGNORECASE)
                self.svgData = replacement.encode(encoding="utf-8")
                subsmade += subcount

            # handle: <path fill="#5E0B23" d="M218.23,..."/>
            attributes = ("fill") # pylint: disable=superfluous-parens
            for attribute in attributes:
                replacement, subcount = re.subn(
                    attribute+"=\""+curReplacement[0]+"\"", r""+attribute+"=\""+curReplacement[1]+"\"", self.svgData.decode(),flags=re.MULTILINE)
                self.svgData = replacement.encode(encoding="utf-8")
                subsmade += subcount

            if subsmade == 0:
                logging.warning(f"Clipart color substitution defined but not made from {curReplacement[0]} to {curReplacement[1]}")
        return self

    @staticmethod
    def convertSVGtoCLP(inputFileSVG:str, outputFileCLP: str = '') -> None:
        """Converts a SVG file to a CLP file.
           If outputFileCLP is left empty, a file a the same base name but .clp extension is created."""
        inFilePath = Path(inputFileSVG)
        if not outputFileCLP: # check for None and empty string
            outputFileCLP = Path(inFilePath.parent).joinpath(inFilePath.stem + ".clp")

        # read SVG into memory
        contents = ClpFile._invalidContent
        with open(inFilePath,"rt") as svgFile: # pylint: disable=unspecified-encoding
            contents = svgFile.read()

        # convert input string to its byte representation using utf-8 encoding.
        # and convert that to a hex string,
        tempCLPdata = contents.encode('utf-8').hex()

        # write CLP file by just adding the header
        with open(outputFileCLP,"wb") as outFile:
            outFile.write('a'.encode('ASCII'))
            outFile.write(tempCLPdata.encode('utf-8'))


# if __name__ == '__main__':
    # only executed when this file is run directly.

    # myClp = ClpFile(r"C:\Program Files\dm\dm-Fotowelt\Resources\photofun\decorations\summerholiday_frames\12195-DECO-SILVER-GD\12195-DECO-SILVER-GD-mask.clp")
    # outImg = myClp.applyAsAlphaMaskToFoto(PIL.Image.open(r"tests\unittest_fotobook_mcf-Dateien\img.png"))
    # outImg.save(r"test.png")

    # clpFile.convertSVGtoCLP("circle.svg")

    # myClp = clpFile()
    # myClp.readClp("circle.clp")
    # myClp.convertToPngInBuffer(200,30)
    # myClp.savePNGfromBufferToFile("test.png")

    # # create pdf
    # from reportlab.pdfgen import canvas
    # import reportlab.lib.pagesizes
    # from reportlab.lib.utils import ImageReader
    # from reportlab.pdfbase import pdfmetrics
    # from reportlab.lib import colors
    # pagesize = reportlab.lib.pagesizes.A4
    # pdf = canvas.Canvas("test" + '.pdf', pagesize=pagesize)
    # pdf.setFillColor(colors.gray)
    # pdf.rect(20,20, 200, 200, fill=1)
    # pdf.drawImage(ImageReader(myClp.pngMemFile), 72, 72, width= 20 * 1/25.4*72, height=2 * 1/25.4*72)
    # pdf.showPage()
    # pdf.save()
