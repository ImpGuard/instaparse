from src.javagen import JavaGenerator
from src.pygen import PythonGenerator
from src.parser import HeimerFormatFileParser
from src.converter import HeimerFormat

from nose.tools import with_setup
from subprocess import Popen, PIPE
from os import chdir, getcwd, mkdir
from os.path import dirname, basename, join
from shutil import rmtree
import difflib
import types

"""
Runs an arbitrary shell command and returns a tuple containing
the STDOUT-output, STDERR-output, and the return code.
"""
def runShellCommand(command):
    pipe = Popen( command, stdout=PIPE, stderr=PIPE )
    out, err = pipe.communicate()
    return out, err, pipe.returncode

def getTest( shouldPass, testName, extension ):
    testsDirectory = join( "test", "tests" )
    if shouldPass:
        testsDirectory = join( testsDirectory, "pass" )
    else:
        testsDirectory = join( testsDirectory, "fail" )
    return (
        shouldPass,
        join( testsDirectory, testName + ".format" ),
        join( testsDirectory, testName + "." + extension ),
        join( testsDirectory, testName + ".input" ),
        join( testsDirectory, testName + ".sln" )
        )

def teardownTest():
    rmtree(GeneratorFixture.testDir)

def setupTest():
    mkdir(GeneratorFixture.testDir)

<<<<<<< HEAD
def printTest(testTuple):
    return str(testTuple)


@with_setup(setupTest)
def checkTest(test):
    opcode, testTuple, val = test()
    if opcode == 1:
        assert False, "Output does not match solution\n" \
            "for " + printTest(testTuple) + "\n\n" + val
    elif opcode == 2:
        assert False, "Format File Error\n" \
            "for " + printTest(testTuple) + "\n\n" + val
    elif opcode == 3:
        assert False, "Compilation Error\n" \
            "for " + printTest(testTuple) + "\n\n" + val
    elif opcode == 4:
        assert False, "Runtime Error\n" \
            "for " + printTest(testTuple) + "\n\n" + val
    teardownTest()

class GeneratorFixture:

    testDir = "test_tmp"
    filename = join(testDir, "Main")

    """
    Initialize a generator fixture by passing it the generator that it is testing,
    functions that can be used to compile and run the generated code for a given
    input file, and a list of tests.
    Parameters:
        generatorType - The CodeGenerator subclass that will be created for each test
        mainFileExtension - The extension of the main file that will be generated
        compileFunc - A function that can be run to compile the generated code
        runFunc - A function that can be run to run the compiled code. It accepts
            one argument, an input file name, and should run the compiled code with
            the input file name as its input and return the
        tests - A list of four-tuples each of which represent a tests. The elements
            in each test are (respectively):
            1) isPass - a boolean representing whether or not this test should pass,
                which allows for tests that are supposed to fail
            2) formatFileName - a string representing the the name of the format file
                that the CodeGenerator will use for this test.
            3) mainFunctionFileName - a string representing the name of the main function
                file. The code in this file will replace the main function code
                generated by the associated CodeGenerator.
            4) inputFileName - a string representing the name of the input file that
                will be passed to runFunc to run the compiled code on.
            5) solutionFileName - a string representing the name of the solution
                file that will be checked against by the output of the compiled code.

    """
    def __init__( self, generatorType, mainFileExtension, tests ):
        self.generatorType = generatorType
        self.mainFileName = GeneratorFixture.filename + "." + mainFileExtension
        self.mainFileDirname = dirname(self.mainFileName)
        self.mainFileBasename = basename(self.mainFileName)
        self.tests = tests

    """
    Functions that wrap the command line calls to compile and run the generated code
    on the file with the associated input filename. Both functions return any output
    associated with the compilation or run from STDOUT and STDERROR as well as the
    return code for the command line call.
    """
    def compile(self):
        raise NotImplementedError()
    def run( self, inputFileName ):
        raise NotImplementedError()

    def insertMainFunction( self, generator, mainFunctionFileName ):
        def insertedMainFunction(self):
            mainFile = open( mainFunctionFileName, "r" )
            for line in mainFile:
                self.output.writeLine(line)
            self.output.writeNewline()
            mainFile.close()

        generator.generateMainFunction = types.MethodType(insertedMainFunction, generator, self.generatorType)

    def createGenerator( self, formatFileName ):
        parser = HeimerFormatFileParser(formatFileName)
        if parser.parseFailed():
            return parser.failureString(), None
        try:
            formatObject = HeimerFormat(parser.objectModel)
            return None, self.generatorType( self.mainFileName, formatObject )
        except ValueError as e:
            return e.message, None

    """
    Creates a generator for all the tests this fixture is testing. Each test will
    run on the provided input files and return a tuple indicating success or failure.
    Every tuple contains another tuple named Test that holds all the different test
    filenames tested.

    The different tuple types are:
        (0, Test, None) - Test succeeded
        (1, Test, Diff) - Test failed, diff is the associated diff output between the
            solution and the generated output
        (2, Test, ErrorMsg) - Error parsing format file, ErrorMsg is the parsing error
            message
        (3, Test, ErrorMsg) - Error compiling generated code, ErrorMsg is the compilation
            error message
        (4, Test, ErrorMsg) - Error running generated code, ErrorMsg is the runtime error
            message
    """
    def generateTests(self):
        def test(shouldPass, formatFileName, mainFunctionFileName, inputFileName, solutionFileName):
            testTuple = (formatFileName, mainFunctionFileName, inputFileName, solutionFileName)
            failed = False
            diff = ""
            # Create generator and insert main function
            err, generator = self.createGenerator(formatFileName)
            if not generator:
                if shouldPass:
                    return (2, testTuple, err)
                else:
                    return (1, testTuple, None)
            self.insertMainFunction( generator, mainFunctionFileName )
            # Generate code
            generator.codeGen()
            # Compile generated code
            out, err, success = self.compile()
            if not success:
                if shouldPass:
                    return (3, testTuple, err)
                else:
                    return (1, testTuple, None)
            # Run generated code
            out, err, success = self.run(inputFileName)
            if not success:
                if shouldPass:
                    return (4, testTuple, err)
                else:
                    return (1, testTuple, None)
            out = out.splitlines()
            # Check output to solution
            solutionFile = open( solutionFileName, "r" )
            solution = "".join(solutionFile.readlines()).splitlines()
            for s in difflib.ndiff( out, solution ):
                diff += s + "\n"
                if s[0] == "+" or s[0] == "-":
                    failed = True
            solutionFile.close()
            # Return success or failure
            if (shouldPass and not failed) or (not shouldPass and failed):
                return (0, testTuple, None)
            else:
                return (1, testTuple, diff)

        for shouldPass, formatFileName, mainFunctionFileName, inputFileName, solutionFileName in self.tests:
            yield lambda: test(shouldPass, formatFileName, mainFunctionFileName, inputFileName, solutionFileName)

class JavaFixture(GeneratorFixture):

    def __init__( self, tests ):
        GeneratorFixture.__init__( self, JavaGenerator, "java", tests)

    def compile(self):
        prevWD = getcwd()
        chdir(self.mainFileDirname)
        out, err, rc = runShellCommand([ "javac", self.mainFileBasename ])
        chdir(prevWD)
        return out, err, rc == 0

    def run( self, inputFileName ):
        prevWD = getcwd()
        chdir(self.mainFileDirname)
        out, err, rc = runShellCommand([ "java", self.mainFileBasename[:-5], join( "..", inputFileName ) ])
        chdir(prevWD)
        return out, err, rc == 0

class PythonFixture(GeneratorFixture):

    def __init__( self, tests ):
        GeneratorFixture.__init__( self, PythonGenerator, "py", tests)

    def compile(self):
        return "", "", True

    def run( self, inputFileName ):
        prevWD = getcwd()
        chdir(self.mainFileDirname)
        out, err, rc = runShellCommand([ "python", self.mainFileBasename, join( "..", inputFileName ) ])
        chdir(prevWD)
        return out, err, rc == 0

