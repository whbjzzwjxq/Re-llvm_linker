import argparse
import os
from typing import Optional, List

from arch.config import ArchConfig, CLANG_PATH, LLC_PATH, arm_arch, x86_arch, riscv64_arch
from utils import c_file_suffix

DEBUG_ENABLE = False


class InputFile:
    def __init__(self, rela_path: str, cfile_path: str, guest: ArchConfig, host: ArchConfig):
        self.rela_path = rela_path
        self.cfile_path = cfile_path
        self.learned_src_line = []  # source lines we have learned in this src file, only line number
        self.guest_asm = []  # guest assembly read from file, a list of lines
        self.guest_asm_dump = []  # guest dumped asm file from obj
        self.guest_ir = []  # guest LLVM IR read from file
        self.host_asm = []  # host assembly read from file
        self.host_asm_dump = []  # host dumped asm file from obj
        self.host_ir = []  # host LLVM IR read from file


def printer(ps: str):
    if DEBUG_ENABLE:
        print(ps)


def gen_internal(cfile_path: str, arch: ArchConfig, cflags: str, opt_level: str):
    cfile_name = os.path.basename(cfile_path).replace('.', '_')
    temp_dir = f'./temp/{cfile_name}'
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir)
    bc_file, ir_file, asm_file, asm_dump_file, obj_file, stdout_file = arch.gen_file_rela_paths(temp_dir)
    printer(f'{cfile_path} (Generate input files for {arch.name})...')
    cflags += f' -I{arch.include}'

    def gen_llvm_ir():
        printer(f"   1. Generate LLVM IR using {arch.name} compiler")
        params = [
            f'-S {cfile_path}',
            f'-o {ir_file}',
            opt_level,
            '-g',
            '-emit-llvm',
            # https://clang.llvm.org/docs/UsersManual.html#cmdoption-fno-discard-value-names
            '-fno-discard-value-names',
            f'--target={arch.target}',
            cflags,
            f'2>{stdout_file}',
        ]
        param_str = ' '.join(params)
        return f"{CLANG_PATH} {param_str}"

    def gen_asm_code() -> str:
        printer(f"   2. Generate {arch.name} asm code")
        params = [
            ir_file,
            f'-o {asm_file}',
            opt_level,
            '--asm-show-inst',
            '--relocation-model=pic',
            '--debugify-level=location+variables',
            f'--mtriple={arch.target}',
        ]
        param_str = ' '.join(params)
        return f"{LLC_PATH} {param_str}"

    def remove_align() -> str:
        printer("3.1. Remove align directive")
        with open(asm_file, mode='r', errors='ignore') as f:
            lines = [_l for _l in f.readlines() if ".align" not in _l]
        if lines:
            with open(asm_file, mode='w') as f:
                f.writelines(lines)
        return ''

    def assemble_asm_to_obj() -> str:
        printer('   3.2. Assemble asm code to obj file')
        params = [
            asm_file,
            f'-o {obj_file}',
        ]
        param_str = ' '.join(params)
        return f"{arch.asm} {param_str}"

    def dump_obj_to_asm() -> str:
        printer('   4. Dump obj file to asm code')
        dump_opt = "-M suffix" if arch.name == 'x86' else ""
        params = [
            '-d',
            '-M reg-names-raw',
            dump_opt,
            '--insn-width=11',
            obj_file,
            f'> {asm_dump_file}',
        ]
        param_str = ' '.join(params)
        return f"{arch.objdump} {param_str}"

    _funcs = (
        gen_llvm_ir,
        gen_asm_code,
        remove_align,
        assemble_asm_to_obj,
        dump_obj_to_asm,
    )
    for _func in _funcs:
        cmd = _func()
        if cmd:
            printer('   ' + cmd)
            os.system(cmd)


def cleanup_input_files(cfile_path: str):
    cfile_dir = os.path.basename(cfile_path).replace('.', '_')
    cmd = f'rm -rf ./temp/{cfile_dir}'
    os.system(cmd)


def init_clean():
    for _dir in os.listdir('./temp'):
        cmd = f'rm -rf ./temp/{_dir}'
        os.system(cmd)


def compile_process(cflags: str, opt_level: str, src_dir: str, file_wanted: Optional[List[str]] = None):
    guest = arm_arch
    host = x86_arch
    for rela_path, sub_path, file_names in os.walk(src_dir):
        for tfile in file_names:
            if not tfile.endswith(c_file_suffix):
                continue
            if file_wanted and tfile not in file_wanted:
                continue
            cfile_path = os.path.join(rela_path, tfile)
            gen_internal(cfile_path, guest, cflags, opt_level)
            gen_internal(cfile_path, host, cflags, opt_level)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="input dir", required=True)
    parser.add_argument("-o", "--output", help="output file prefix", default="output")
    parser.add_argument("-d", "--debug", help="enable debug", action='store_true')
    parser.add_argument("-fw", help="wanted files\' name, split it with comma")
    parser.add_argument("-O", "--OPT", help="optimization level", default=0, type=int)
    parser.add_argument("-C", "--CFLAGS", help="extra cflags", default="")
    parser.add_argument("-I", "--INCLUDES", help="extra include dirs", default="", nargs="*")
    args = parser.parse_args()
    global DEBUG_ENABLE
    DEBUG_ENABLE = args.debug
    init_clean()
    cflags = args.CFLAGS
    for i in args.INCLUDES:
        cflags += f' -I{i}'
    opt = f'-O{args.OPT}'
    src_dir = args.input
    file_wanted = None if not args.fw else args.fw.split(',')
    compile_process(cflags, opt, src_dir, file_wanted)


if __name__ == '__main__':
    main()
