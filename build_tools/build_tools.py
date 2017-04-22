import fnmatch
import os, sys, shutil, subprocess, platform, traceback, json
from distutils.dir_util import copy_tree

def PrintException():
    print('-'*60)
    print("Exception occured:")
    print('-'*60)
    traceback.print_exc(file=sys.stdout)
    print('-'*60)

class Platform:
    @staticmethod
    def Is(name):
        return Platform.Current() == name.lower()

    @staticmethod
    def Current():
        return platform.system().lower()

    @staticmethod
    def ExecCommand(command):
        print("Executing command: '" + command + "'")

        try:
            subprocess.check_call(command, shell=True)
            return True
        except:
            return False

    @staticmethod
    def CheckExecutableExists(name):
        if Platform.Is('windows'):
            return Platform.ExecCommand("where " + name)
        elif Platform.Is('linux'):
            return Platform.ExecCommand('type ' + name + ' >/dev/null 2>&1 || { echo >&2 "not found"; exit 1; }') # test on linux, remove extra message

#Supported compilers
class Compiler:
    def compile(self):
        pass

class GccCompiler(Compiler):
    def compile(self, **kwargs):
        threads = kwargs.get('threads', 9)
        Platform.ExecCommand("make -j" + str(threads))

    def lib_extension(self):
        return '.a'

    def generator(self):
        return "Unix Makefiles"

    def executable_name(self):
        return "make"

class MinGWCompiler(Compiler):
    def compile(self, **kwargs):
        threads = kwargs.get('threads', 9)
        Platform.ExecCommand("mingw32-make -j" + str(threads))

    def lib_extension(self):
        return '.a'

    def generator(self):
        return "MinGW Makefiles"

    def executable_name(self):
        return "mingw32-make"

class JomCompiler(Compiler):
    def compile(self, **kwargs):
        threads = kwargs.get('threads', 9)
        Platform.ExecCommand("jom -j" + str(threads))

    def lib_extension(self):
        return '.lib'

    def generator(self):
        return "NMake Makefiles"

    def executable_name(self):
        return "jom"

class NMakeCompiler(Compiler):
    def lib_extension(self):
        return '.lib'

    def compile(self, **kwargs):
        Platform.ExecCommand("nmake")

    def generator(self):
        return "NMake Makefiles"

    def executable_name(self):
        return "nmake"


#Build commands
class BuildCommand(object):
    """docstring for BuildCommand"""
    def __init__(self):
        super(BuildCommand).__init__()

    def Exec(self):
        print("Should be implemented by specific command")

class PlatformCommand(BuildCommand):
    def __init__(self, **kwargs):
        super(PlatformCommand, self).__init__()

    def Exec(self, dir, command):
        FileSystem.PushDir()

        try:
            FileSystem.ChangeDir(dir)
            Platform.ExecCommand(command)
        except:
            PrintException()
            raise
        finally:
            FileSystem.PopDir()

class CMakeCommand(BuildCommand):

    """docstring for CMakeCommand"""
    def __init__(self, compiler, **kwargs):
        super(CMakeCommand, self).__init__()
        self.compiler = compiler
        self.generator = self.compiler.generator()
        self.common_defines = {}
        self.common_defines.update(kwargs.get('defines', {}))

    def __formatDefines(self, defines):
        command = ""
        for key, val in defines.items():
            command += " -D" + key + "=" + val

        return command

    def __copyCompileFlags(self, cmake_dir, build_dir, **kwargs):

        filename = "compile_commands.json"
        fullpath = str(build_dir.Join(filename))
        compile_commands_dir = PathBuilder(kwargs.get('flags_path', cmake_dir)).Join(".clang_complete")

        try:
            self._generateClangCompletionFlags(fullpath, compile_commands_dir)
        except:
            PrintException()

    def _generateClangCompletionFlags(self, compile_commands_path, output_path):
        commands = ""

        with open(compile_commands_path, "r") as cfile:
            content = cfile.read()
            cjson = json.loads(content)
            commands = cjson[0]["command"].split()

        prevcmd = ""
        cmds = self._parseCommands(commands)

        with open(str(output_path), "w") as cfile:
            cfile.write(cmds)

    def _parseCommands(self, commands):
        cmds = ""
        i = 0
        while i < len(commands):
            cmd = commands[i]
            next_cmd = commands[i+1] if i < len(commands) - 1 else None

            if cmd.startswith(("-c", "-g", "-o", "-pg", "-O")):
                i = i + 1
            elif cmd.startswith("-"):
                if next_cmd is None or next_cmd.startswith("-"):
                    cmds += cmd + "\n"
                    i = i + 1
                else:
                    cmds += cmd + " " + next_cmd + "\n"
                    i = i + 2
            else:
                i = i + 1

        return cmds

    def Exec(self, cmake_dir, build_dir,  **kwargs):
        FileSystem.PushDir()

        try:
            FileSystem.CreateAndChangeDir(build_dir)

            defines = {'CMAKE_BUILD_TYPE':'RelWithDebInfo'}
            defines.update(self.common_defines)
            defines.update(kwargs.get('defines', {}))

            command  = "cmake " + str(cmake_dir)
            command += self.__formatDefines(defines)
            command += " -G \"" + self.generator + "\""

            Platform.ExecCommand(command)
            self.__copyCompileFlags(cmake_dir, build_dir, **kwargs)
            self.compiler.compile(**kwargs)

        except:
            PrintException()
            raise
        finally:
            FileSystem.PopDir()

#Utilities
def GetCompiler(**kwargs):
    compilerName = kwargs.get("compiler", "")

    compilers = {
        "gcc"   : GccCompiler(),
        "mingw" : MinGWCompiler(),
        "jom"   : JomCompiler(),
        "nmake" : NMakeCompiler()
    }

    platform_compilers = {
        "linux"  : ['gcc'],
        "windows": ['jom', 'nmake', 'mingw']
    }


    if len(compilerName) == 0 or compilerName.isspace():
        current_platform_compilers = platform_compilers[Platform.Current()]

        for compiler in current_platform_compilers:
            executable_name = compilers.get(compiler).executable_name()

            if Platform.CheckExecutableExists(executable_name) == False:
                continue

            return compilers.get(compiler, None)
    else:
        return compilers.get(compilerName, None)

    return None

class PathBuilder:
    def __init__(self, base_path):
        self.base_path = str(base_path)

    def Join(self, rel_path):
        return PathBuilder(os.path.join(self.base_path, str(rel_path)))

    def Parent(self):
        return PathBuilder(os.path.dirname(self.base_path))

    def GetBasePath(self):
        return self.base_path

    def __str__(self):
        return self.base_path

class FileSystem:
    @staticmethod
    def GetFilesByExtension(dir, extension):
        file_matches = []

        for root, dirnames, filenames in os.walk(str(dir)):
            for filename in fnmatch.filter(filenames, '*' + extension):
                if filename != "objects" + extension:
                    file_matches.append([filename,os.path.join(root, filename)])

        return file_matches

    @staticmethod
    def CopyFiles(files, dest_path):
        matches = []
        matches.extend(files)
        destination = PathBuilder(dest_path)

        FileSystem.CreateDir(destination)

        for f in matches:
            moved_file_path = str(destination.Join(f[0]))
            try:
                shutil.move(f[1], moved_file_path)
            except:
                PrintException()
                raise

    @staticmethod
    def CopyFolder(source, dest):
        copy_tree(str(source), str(dest))

    @staticmethod
    def RemoveDir(dir):
        try:
            shutil.rmtree(str(dir))
        except:
            pass

    directories = []

    @staticmethod
    def Cwd():
        return os.getcwd()

    @staticmethod
    def PushDir():
        FileSystem.directories.append(FileSystem.Cwd())

    @staticmethod
    def PopDir():
        FileSystem.ChangeDir(FileSystem.directories.pop())

    @staticmethod
    def CreateDir(dir):
        try:
            os.makedirs(str(dir))
        except FileExistsError as e:
            PrintException()
        except OSError as e:
            PrintException()
            raise

    @staticmethod
    def CreateAndChangeDir(dir):
        FileSystem.CreateDir(dir)
        FileSystem.ChangeDir(dir)
        return True

    @staticmethod
    def CreateSymlink(src, dest):
        try:
            os.symlink(str(src), str(dest))
        except:
            PrintException()

    @staticmethod
    def ChangeDir(dir):
        os.chdir(str(dir))

    @staticmethod
    def Exists(path):
        return os.path.exists(str(path))

#End of build tools
