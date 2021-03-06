from codegen import CodeGenerator
from javagenStatic import *
from util import *

from optparse import OptionParser
from os.path import join, splitext, basename

""" Class for generating Java code. """
class JavaGenerator(CodeGenerator):

    def initialize(self):
        """ Perform additional initialization if required. """
        InstaParseFile.commentString = "//"
        self.main.setExtension("java")
        self.util.setExtension("java")
        self.classFiles = []

    def codeGen(self):
        """ This method is called to generate and write the parser to the specified file. """
        self.generateClasses()
        self.generateUtilFile()
        self.generateMainFile()
        self.main.save()
        self.util.save()
        map(lambda c: c.save(), self.classFiles)

    ################################################################################
    # Generate Data File
    ################################################################################

    def generateClass( self, className, fields ):
        """ Helper function for generating the code segement defining a class (or the corresponding
        data structure). The first argument is the class name and the second argument is a list of
        fields (in order) of that class. """
        self.typeNameToParseFuncName[className] = "parse%s" % className
        classFile = InstaParseFile(join(self.foldername, className + ".java"))
        self.classFiles.append(classFile)
        self.currentFile = classFile

        shouldImportArrayList = False

        self._beginBlock("public class " + className )

        for field in fields:
            if field.isRepeating() or field.isList():
                shouldImportArrayList = True
            classFile.writeLine("public " + self._getTypeName(field) + " " + field.name() + ";")

        if shouldImportArrayList:
            classFile.writeImportLine("")
            classFile.writeImportLine("import java.util.ArrayList;")

        self._endBlock()

    ################################################################################
    # Generate Util File
    ################################################################################

    def generateUtilFile(self):
        self.currentFile = self.util
        self.generateUtilFileHeader()
        self._beginBlock("public class " + CodeGenerator.UTIL_FILE_NAME)
        self.generateHelperFunctions()
        self.generateClassParserFunctions()
        self._endBlock()

    def generateUtilFileHeader(self):
        """ For generating the util file header, such as the import statements. """
        # Import library headers
        self.currentFile.writeLine("import java.util.ArrayList;")
        self.currentFile.writeLine("import java.util.Arrays;")
        self.currentFile.writeLine("import java.io.RandomAccessFile;")
        self.currentFile.writeLine("import java.io.EOFException;")
        self.currentFile.writeLine("import java.io.IOException;")

        self.currentFile.writeNewline()

    def generateHelperFunctions(self):
        """ For generating the helper functions that will be useful when parsing in the util file. """
        # Static helpers for primitives
        helpers = javagenStaticHelpers()
        map(lambda s: self.currentFile.writeLine(s), helpers.splitlines())
        self.currentFile.writeNewline()

    def generateClassParserFunction( self, className, lines ):
        """ For generating a helper functions for parsing a user defined class. The first argument
        is the class name and the second argument is a list of FormatLine's. """
        writeLine = self.currentFile.writeLine
        write = self.currentFile.write

        def isSimplePrimitive(field):
            return field.isInteger() or field.isFloat() or field.isString() or field.isBool()

        def generateSetup():
            # Helper to do some setup in every parser function
            writeLine(className + " result = new " + className + "();")
            didSplit = False
            didRepeat = False
            didRepeatPlus = False

            for line in lines:
                didRepeat = didRepeat or line.isRepeating()
                didRepeatPlus = didRepeatPlus or  line.isOneOrMoreRepetition()
                didSplit = didSplit or line.numFields() > 1 or (not line.isEmpty() and line.getField(0).isList())

            if didSplit:
                writeLine("String[] fields;")
            if didRepeat:
                writeLine("long prevFilePos = getFilePointer(f);")
                writeLine("int prevLineNumber = lineNumber[0];")
            if didRepeatPlus:
                writeLine("boolean didRepeatOnce = false;")

        def handleEmptyLine():
            # Handle the empty line case
            self._beginBlock("if (!readLine(f, \"" + className + "\").trim().equals(\"\"))")
            writeLine("throw new RuntimeException(\"Parser Error on line \" + lineNumber[0] +" +
                "\": Should be an empty line.\");")
            self._endBlock()
            writeLine("lineNumber[0] += 1;")

        def handleSimpleLineOneField(field):
            # Helper for handleSimpleLine
            if isSimplePrimitive(field):
                # Field is simple, just parse it
                writeLine("result." + field.name() + " = "
                    + self.typeNameToParseFuncName[field.typeName()] + "(readLine(f, \"" + className + "\"), lineNumber);")
                writeLine("lineNumber[0] += 1;")
            elif field.isPrimitive():
                # Field is primitive list, split line
                writeLine("fields = readLine(f, \"" + className + "\").split(\"" + self.format.lineDelimiter() + "\");")
                write("result." + field.name() + " = "
                    + self.typeNameToParseFuncName["list(%s)" % field.listType()] + "(fields, lineNumber);")
                writeLine("lineNumber[0] += 1;")
            else:
                # Field is a class, recurse
                writeLine("result." + field.name() + " = "
                    + self.typeNameToParseFuncName[field.typeName()] + "(f, lineNumber);")

        def handleSimpleLineMultipleField(index, field):
            # Helper for handleSimpleLine
            if isSimplePrimitive(field):
                writeLine("result." + field.name() + " = "
                    + self.typeNameToParseFuncName[field.typeName()]
                    + "(fields[" + str(index) + "], lineNumber);")
            elif field.isPrimitive():
                # Field is primitive list, use rest of fields)
                writeLine("result." + field.name() + " = "
                    + self.typeNameToParseFuncName["list(%s)" % field.listType()]
                    + "(Arrays.copyOfRange(fields, " + str(index) + ", fields.length), lineNumber);")
            else:
                # Field is a class? Cannot be!
                raise Exception("This should never happen.")

            writeLine("lineNumber[0] += 1;")

        def handleSimpleLine(line):
            if line.numFields() == 1:
                # Only one field, no need to split unnecessarily
                handleSimpleLineOneField(line.getField(0))
            else:
                # Multiple fields, split it
                writeLine("fields = readLine(f, \"" + className + "\").split(\"" + self.format.lineDelimiter() + "\");")
                if (line.getField(-1).isList()):
                    self._beginBlock("if (fields.length < " + str(line.numFields()) + ")")
                else:
                    self._beginBlock("if (fields.length != " + str(line.numFields()) + ")")
                writeLine("throw new RuntimeException(\"Parser Error on line \" + lineNumber[0] + " +
                    "\": Expecting " + str(line.numFields()) + " fields (\" + fields.length + \" found).\");")
                self._endBlock()
                for index, field in enumerate(line):
                    handleSimpleLineMultipleField(index, field)

        def handleRepeatingLineForField(field):
            # Helper for handleRepeating
            if isSimplePrimitive(field):
                # Field is simple, just parse it
                writeLine("result." + field.name() + ".add("
                    + self.typeNameToParseFuncName[field.typeName()] + "(readLine(f, \"" + className + "\"), lineNumber));")
                writeLine("lineNumber[0] += 1;")
            elif field.isPrimitive():
                # Field is primitive list, split line
                writeLine("fields = readLine(f, \"" + className + "\").split(\"" + self.format.lineDelimiter() + "\");")
                writeLine("result." + field.name() + ".add("
                    + self.typeNameToParseFuncName["list(%s)" % field.listType()] + "(fields, lineNumber));")
                writeLine("lineNumber[0] += 1;")
            else:
                # Field is a class, recurse
                writeLine("result." + field.name() + ".add("
                    + self.typeNameToParseFuncName[field.typeName()] + "(f, lineNumber));")

        def handleRepeatingLine(line):
            # Must be a primitive or class repeated
            if line.isIntegerRepetition() or line.isVariableRepetition():
                # Constant repetition amount
                field = line.getField(0)
                # Generate the repetition string
                repetitionString = ""
                if line.isIntegerRepetition():
                    repetitionString = str(line.repetitionAmountString())
                else:
                    repetitionString =  "result." + line.repetitionAmountString()
                # Initialize the arraylist
                writeLine("result." + field.name() + " = new " + self._getTypeName(field) + "();")
                # Begin loop
                self._beginBlock("for (int i = 0; i < " + repetitionString + "; i++)")
                # Wrap with try
                self._beginBlock("try")
                # Main handler
                handleRepeatingLineForField(field)
                # Check for newline
                if (line.isSplitByNewline()):
                    self._beginBlock("if (i != " + repetitionString + " - 1)")
                    handleEmptyLine()
                    self._endBlock()
                # End try
                self._endBlock()
                # Catch any error to throw appropriate error message
                self._beginBlock("catch (Exception e)")
                writeLine("throw new RuntimeException(\"Parser Error on line \" + lineNumber[0] +"
                    + "\": Expecting exactly \" + " + repetitionString + " + \" \\\"" + field.typeName()
                    + "\\\" when parsing \\\"" + className + "." + field.name()
                    + "\\\" (\" + i + \" found).\");")
                self._endBlock()
                # End loop
                self._endBlock()
            elif line.isZeroOrMoreRepetition():
                field = line.getField(0)
                # Wrap with try block
                self._beginBlock("try")
                # Initialize object
                writeLine("result." + field.name() + " = new " + self._getTypeName(field) + "();")
                # Save initial position
                writeLine("prevFilePos = getFilePointer(f);")
                writeLine("prevLineNumber = lineNumber[0];")
                # Begin infinite loop
                self._beginBlock("while (true)")
                # Main handler
                handleRepeatingLineForField(field)
                writeLine("prevFilePos = getFilePointer(f);")
                writeLine("prevLineNumber = lineNumber[0];")
                # Check for newline
                if (line.isSplitByNewline()):
                    handleEmptyLine()
                # End infinite loop and try block
                self._endBlock()
                self._endBlock()
                # Catch any errors, reset line number and continue
                self._beginBlock("catch (Exception e)")
                writeLine("seek(f, prevFilePos);")
                writeLine("lineNumber[0] = prevLineNumber;")
                self._endBlock()
            elif line.isOneOrMoreRepetition:
                field = line.getField(0)
                # Wrap with try block
                self._beginBlock("try")
                # Initialize object and checker to ensure at least one repetition
                writeLine("didRepeatOnce = false;")
                writeLine("result." + field.name() + " = new " + self._getTypeName(field) + "();")
                # Begin infinite loop
                self._beginBlock("while (true)")
                # Main handler
                handleRepeatingLineForField(field)
                writeLine("prevFilePos = getFilePointer(f);")
                writeLine("prevLineNumber = lineNumber[0];")
                writeLine("didRepeatOnce = true;")
                # Check for newline
                if (line.isSplitByNewline()):
                    handleEmptyLine()
                # End infinite loop and try block
                self._endBlock()
                self._endBlock()
                # Catch any errors, either (1) reset line number and continue (2) error if did not repeat once
                self._beginBlock("catch (Exception e)")
                self._beginBlock("if (!didRepeatOnce)")
                writeLine("throw new RuntimeException(\"Parser Error on line \" + lineNumber[0] +"
                    + "\": Expecting at least 1 \\\"" + field.typeName()
                    + "\\\" when parsing \\\"" + className + "." + field.name()
                    + "\\\" (0 found).\");")
                self._endBlock()
                writeLine("seek(f, prevFilePos);")
                writeLine("lineNumber[0] = prevLineNumber;")
                self._endBlock()
            else:
                raise Exception("This should never happen.")


        self._beginBlock("public static " + className + " parse" + className + "(RandomAccessFile f, int[] lineNumber)")
        generateSetup()

        # Handle the three different cases, helpers are inner functions defined above
        for line in lines:
            if line.isEmpty():
                handleEmptyLine()
            elif line.isRepeating():
                handleRepeatingLine(line)
            else:
                handleSimpleLine(line)

        writeLine("return result;")
        self._endBlock()
        self.currentFile.writeNewline()

    ################################################################################
    # Generate Main File
    ################################################################################

    def generateMainFile(self):
        """ Generate main file where the main function resides. """
        self.currentFile = self.main
        self.generateMainFileHeader()
        self._beginBlock("public class " + splitext(basename(self.currentFile.filename))[0])
        self.generateMainFunction()
        self.generateInputParserFunction()
        self._endBlock()

    def generateMainFileHeader(self):
        """ For generating the main file header, such as the import statements. """
        # Import library headers
        self.currentFile.writeLine("import java.io.RandomAccessFile;")
        self.currentFile.writeLine("import java.io.FileNotFoundException;")
        self.currentFile.writeLine("import java.io.IOException;")
        self.currentFile.writeLine("import java.io.EOFException;")
        self.currentFile.writeNewline()

    def generateMainFunction(self):
        """ For generating the empty main method that the user can fill in. """
        self._beginBlock("public static void main(String[] args)")
        self.currentFile.comment("Call " + CodeGenerator.PARSE_INPUT + "(filename) to parse the file of that name.")
        self._endBlock()
        self.currentFile.writeNewline()

    def generateInputParserFunction(self):
        """ For generating the function to parse an input file. """
        writeLine = self.currentFile.writeLine
        # Begin function declaration
        self._beginBlock("private static " + self.bodyTypeName
            + " " + CodeGenerator.PARSE_INPUT + "(String filename)")

        # Main try block
        self._beginBlock("try")
        # Initial setup
        writeLine("RandomAccessFile f = new RandomAccessFile(filename, \"r\");")
        writeLine("int[] lineNumber = {1};")
        # Begin parsing
        writeLine(self.bodyTypeName + " result = "
            + CodeGenerator.UTIL_FILE_NAME + "." + self.typeNameToParseFuncName[self.bodyTypeName] + "(f, lineNumber);")
        # Handle trailing newlines
        writeLine("String line;")
        self._beginBlock("while ((line = f.readLine()) != null)")
        self._beginBlock("if (!line.equals(\"\"))")
        writeLine("throw new RuntimeException(\"Parser Error on line \" + lineNumber[0] + \": Finished parsing but did not reach end of file.\");")
        self._endBlock()
        self._endBlock()
        # Finish up
        writeLine("f.close();")
        writeLine("return result;")
        self._endBlock()

        # Catch file not found
        self._beginBlock("catch (FileNotFoundException e)")
        writeLine("System.err.println(\"Input file '\" + filename + \"' not found.\");")
        writeLine("System.exit(1);")
        self._endBlock()
        # Catch random IOExceptions
        self._beginBlock("catch (IOException e)")
        writeLine("System.err.println(\"Could not open \\\"\" + filename + \"\\\".\");")
        self._endBlock()
        # All other exception catches (EOF exception caught here)
        self._beginBlock("catch (Exception e)")
        writeLine("System.err.println(e.getMessage());")
        writeLine("System.exit(1);")
        self._endBlock()

        # Should never reach this line
        writeLine("System.err.println(\"Unknown error occurred.\");")
        writeLine("System.exit(1);")
        writeLine("return null;")

        # End function declaration
        self._endBlock()

    ################################################################################
    # Helper Functions
    ################################################################################

    def _getBasicTypeName( self, typeName ):
        if isInteger(typeName):
            return "Integer"
        if isFloat(typeName):
            return "Float"
        elif isString(typeName):
            return "String"
        elif isBool(typeName):
            return "Boolean"
        elif isList(typeName):
            return "ArrayList<" + self._getBasicTypeName(listType(typeName)) + ">"
        else:
            return None


    def _getTypeName( self, field ):
        typeName = self._getBasicTypeName(field.typeName())
        if typeName == None:
            typeName = field.typeName()

        if field.isRepeating():
            return "ArrayList<" + typeName + ">"
        else:
            return typeName

    def _beginBlock( self, line ):
        self.currentFile.writeLine(line)
        self.currentFile.writeLine("{")
        self.currentFile.indent()

    def _endBlock(self):
        self.currentFile.dedent()
        self.currentFile.writeLine("}")
