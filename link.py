import argparse
import json
import os
from collections import defaultdict
from typing import Optional, List

import regex as re
from regex import Pattern, Match

from arch.config import ArchConfig, CLANG_PATH, LLC_PATH, arm_arch, x86_arch, OPT_PATH
from utils import c_file_suffix

_DEBUG_ENABLE = False
_GUEST = arm_arch
_HOST = x86_arch


class LLVMIRInfoLoader:

    def __init__(self, info_path: str):
        self.funcs = []
        self.bbs = []
        self.line2insts = defaultdict(list)
        with open(info_path, mode='r') as f:
            while True:
                line = f.readline()
                if line.startswith('{'):
                    self.resolve_line(line)
                elif line == '':
                    break
                else:
                    pass

    def resolve_line(self, line: str):
        func_info = json.loads(line)
        self.funcs.append(func_info)
        for bb in func_info['bbs']:
            self.bbs.append(bb)
            for inst in bb['insts']:
                line = inst['line']
                self.line2insts[line].append(inst)


class AsmLoader:
    func_regex: Pattern = re.compile(r'\d+ <(.*)>:')
    block_regex: Pattern = re.compile(r'(.*)\(\):')
    line_num_regex: Pattern = re.compile(r'.*.c[cp]{0,2}:(\d+)')

    def __init__(self, asm_path: str, arch: ArchConfig):
        self.arch = arch
        self.funcs = []
        self.bbs = []
        self.line2insts = defaultdict(list)
        self._cur_address = 0
        self._cur_line_num = 0
        self._cur_func = None
        self._cur_block = None
        with open(asm_path, mode='r') as f:
            while True:
                line = f.readline()
                if line == '':
                    break
                else:
                    self.resolve_line(line)

    @property
    def cur_addr_as_hex(self) -> str:
        return hex(self._cur_address)[2:]

    def resolve_line(self, line: str):
        line = line[:-1]
        line = line.lstrip(' ')
        if line.startswith(self.cur_addr_as_hex + ':'):
            self.resolve_inst(line)
        else:
            _func_match: Optional[Match] = self.func_regex.match(line)
            _block_match: Optional[Match] = self.block_regex.match(line)
            _line_num_match: Optional[Match] = self.line_num_regex.match(line)
            if _func_match is not None:
                if any((_block_match, _line_num_match)):
                    raise ValueError('Duplicated match')
                name = _func_match.group(1)
                self.resolve_func(name)
            elif _block_match is not None:
                if any((_func_match, _line_num_match)):
                    raise ValueError('Duplicated match')
                name = _block_match.group(1)
                self.resolve_block(name)
            elif _line_num_match is not None:
                if any((_func_match, _block_match)):
                    raise ValueError('Duplicated match')
                line_num = int(_line_num_match.group(1))
                self._cur_line_num = line_num
            else:
                pass

    def resolve_func(self, name: str):
        _func_info = {'name': name, 'bbs': []}
        self._cur_func = _func_info

    def resolve_block(self, name: str):
        block = {'name': name, 'insts': []}
        self._cur_func['bbs'].append(block)
        self._cur_block = block

    def resolve_inst(self, line: str):
        inst = self.arch.asm_line_resolver(line)
        self._cur_address += (len(inst.hex_code) // 2)
        self.line2insts[self._cur_line_num].append(inst)
        self._cur_block['insts'].append(inst)


def _printer(ps: str):
    if _DEBUG_ENABLE:
        print(ps)


def _cfile_path2temp_paths(cfile_path: str, arch: ArchConfig):
    cfile_name = os.path.basename(cfile_path).replace('.', '_')
    temp_dir = f'./temp/{cfile_name}'
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir)
    return arch.gen_file_rela_paths(temp_dir)


def _gen_arch_file(cfile_path: str, arch: ArchConfig, cflags: str, opt_level: str):
    result = _cfile_path2temp_paths(cfile_path, arch)
    ir_path, ir_info_path, asm_path, asm_dump_path, obj_path, tmp_path = result
    _printer(f'{cfile_path} (Generate input files for {arch.name})...')
    cflags += f' -I{arch.include}'

    def gen_llvm_ir():
        _printer(f"   1.1 Generate LLVM IR using {arch.name} compiler")
        params = [
            f'-S {cfile_path}',
            f'-o {ir_path}',
            opt_level,
            '-g',
            '-emit-llvm',
            # https://clang.llvm.org/docs/UsersManual.html#cmdoption-fno-discard-value-names
            '-fno-discard-value-names',
            f'--target={arch.target}',
            cflags,
            f'> /dev/null',
            f'2>&1',
        ]
        param_str = ' '.join(params)
        return f"{CLANG_PATH} {param_str}", ir_path

    def gen_llvm_ir_info():
        _printer(f"   1.2 Generate LLVM IR information using {arch.name} compiler")
        params = [
            f'-S {cfile_path}',
            f'-o {tmp_path}',
            opt_level,
            '-emit-llvm',
            # https://clang.llvm.org/docs/UsersManual.html#cmdoption-fno-discard-value-names
            '-fno-discard-value-names',
            f'--target={arch.target}',
            cflags,
            f'> /dev/null',
            f'2>&1',
        ]
        param_str = ' '.join(params)
        params2 = [
            '--enable-debugify',
            '-load LLVMIR2JSON.so',
            '-ir2json',
            f'< {tmp_path}',
            '> /dev/null',
            f'2> {ir_info_path}',
        ]
        param_str2 = ' '.join(params2)
        return f"{CLANG_PATH} {param_str} && {OPT_PATH} {param_str2}", ir_info_path

    def gen_asm_code():
        _printer(f"   2. Generate {arch.name} asm code")
        params = [
            ir_path,
            f'-o {asm_path}',
            opt_level,
            '--asm-show-inst',
            '--relocation-model=pic',
            '--debugify-level=location+variables',
            f'--mtriple={arch.target}',
        ]
        param_str = ' '.join(params)
        return f"{LLC_PATH} {param_str}", asm_path

    def remove_align():
        _printer("   3.1. Remove align directive")
        with open(asm_path, mode='r', errors='ignore') as f:
            lines = [_l for _l in f.readlines() if ".align" not in _l]
        if lines:
            with open(asm_path, mode='w') as f:
                f.writelines(lines)
        return '', ''

    def assemble_asm_to_obj():
        _printer('   3.2. Assemble asm code to obj file')
        params = [
            asm_path,
            f'{arch.as_para}',
            f'-o {obj_path}',
        ]
        param_str = ' '.join(params)
        return f"{arch.asm} {param_str}", obj_path

    def dump_obj_to_asm():
        _printer('   4. Dump obj file to asm code')
        params = [
            '-d -l',
            f'--target={arch.target}',
            arch.objdump_para,
            '--insn-width=8',
            obj_path,
            f'> {asm_dump_path}',
        ]
        param_str = ' '.join(params)
        return f"{arch.objdump} {param_str}", asm_dump_path

    _funcs = (
        gen_llvm_ir,
        gen_llvm_ir_info,
        gen_asm_code,
        remove_align,
        assemble_asm_to_obj,
        dump_obj_to_asm,
    )
    for _func in _funcs:
        cmd, required_file = _func()
        if cmd and (_DEBUG_ENABLE or not os.path.exists(required_file)):
            _printer('   ' + cmd)
            os.system(cmd)
    return ir_info_path, asm_dump_path


def _clean_cache():
    for _dir in os.listdir('./temp'):
        cmd = f'rm -rf ./temp/{_dir}'
        os.system(cmd)


def _compile_process(guest: ArchConfig, host: ArchConfig, cflags: str, includes: List[str], opt: int, src_dir: str,
                     file_wanted: Optional[List[str]] = None):
    for i in includes:
        cflags += f' -I{i}'
    opt_level = f'-O{opt}'
    for rela_path, sub_path, file_names in os.walk(src_dir):
        for tfile in file_names:
            if not tfile.endswith(c_file_suffix):
                continue
            if file_wanted and tfile not in file_wanted:
                continue
            cfile_path = os.path.join(rela_path, tfile)
            g_ir_info_path, g_asm_dump_path = _gen_arch_file(cfile_path, guest, cflags, opt_level)
            h_ir_info_path, h_asm_dump_path = _gen_arch_file(cfile_path, host, cflags, opt_level)
            yield cfile_path, g_ir_info_path, g_asm_dump_path, h_ir_info_path, h_asm_dump_path


def link(guest: ArchConfig, host: ArchConfig, cflags: str, includes: List[str], opt: int, src_dir: str,
         file_wanted: Optional[List[str]] = None):
    for _iter in _compile_process(guest, host, cflags, includes, opt, src_dir, file_wanted):
        cfile_path, g_ir_info_path, g_asm_dump_path, h_ir_info_path, h_asm_dump_path = _iter
        g_ir_loader = LLVMIRInfoLoader(g_ir_info_path)
        h_ir_loader = LLVMIRInfoLoader(h_ir_info_path)
        g_asm_loader = AsmLoader(g_asm_dump_path, guest)
        h_asm_loader = AsmLoader(h_asm_dump_path, host)
        with open(cfile_path, mode='r') as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            line_idx = idx + 1
            g_ir_insts = g_ir_loader.line2insts.get(line_idx, [])
            h_ir_insts = h_ir_loader.line2insts.get(line_idx, [])
            g_insts = g_asm_loader.line2insts.get(line_idx, [])
            h_insts = h_asm_loader.line2insts.get(line_idx, [])
            yield idx, line, g_ir_insts, h_ir_insts, g_insts, h_insts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="input dir", required=True)
    parser.add_argument("-o", "--output", help="output file prefix", default="output")
    parser.add_argument("-d", "--debug", help="enable debug", action='store_true')
    parser.add_argument("-fw", help="wanted files\' name, split it with comma")
    parser.add_argument("-O", "--opt", help="optimization level", default=0, type=int)
    parser.add_argument("-C", "--cflags", help="extra cflags", default="")
    parser.add_argument("-I", "--includes", help="extra include dirs", default="", nargs="*")
    args = parser.parse_args()
    _DEBUG_ENABLE = args.debug
    _file_wanted = None if not args.fw else args.fw.split(',')
    for _ in link(_GUEST, _HOST, args.cflags, args.includes, args.opt, args.input, _file_wanted):
        pass
