import os
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class ASMInst:
    addr: str
    hex_code: str
    opcode: str
    operands: str
    appends: str

    @property
    def addr_as_int(self):
        return int(self.addr, 16)


@dataclass
class ArchConfig:
    name: str
    target: str
    asm: str
    objdump: str
    include: str
    asm_line_resolver: Callable[[str], ASMInst]
    objdump_para: str = ''
    as_para: str = ''

    @property
    def bc_prefix(self):
        return self.name + '_bc'

    @property
    def ir_filename(self):
        return self.name + '.ll'

    @property
    def ir_info_filename(self):
        return self.name + '-info.ll'

    @property
    def asm_filename(self):
        return self.bc_prefix + '.s'

    @property
    def asm_dump_filename(self):
        return self.bc_prefix + '_dump.s'

    @property
    def obj_filename(self):
        return self.bc_prefix + '.o'

    @property
    def tmp_filename(self):
        return self.name + '.tmp'

    @property
    def filenames(self):
        return [
            self.ir_filename,
            self.ir_info_filename,
            self.asm_filename,
            self.asm_dump_filename,
            self.obj_filename,
        ]

    def gen_file_rela_paths(self, temp_dir: str):
        ir_path = os.path.join(temp_dir, self.ir_filename)
        ir_info_path = os.path.join(temp_dir, self.ir_info_filename)
        asm_path = os.path.join(temp_dir, self.asm_filename)
        asm_dump_path = os.path.join(temp_dir, self.asm_dump_filename)
        obj_path = os.path.join(temp_dir, self.obj_filename)
        tmp_path = os.path.join(temp_dir, self.tmp_filename)
        return ir_path, ir_info_path, asm_path, asm_dump_path, obj_path, tmp_path


def resolve_arm_asm_inst(line: str):
    components: List[str] = line.split('\t')
    if len(components) == 4:
        components.append('')
    addr, hex_code, opcode, operands, appends = components
    addr = addr[:-1]
    hex_code = hex_code.rstrip(' ')
    appends = appends[2:]
    return ASMInst(addr, hex_code, opcode, operands, appends)


def resolve_x86_asm_inst(line: str):
    components: List[str] = line.split('\t')
    addr, hex_code, asm_code = components
    addr = addr[:-1]
    hex_code = hex_code.rstrip(' ')
    opcode, operands = asm_code.split(' ', maxsplit=1)
    operands.lstrip(' ')
    return ASMInst(addr, hex_code, opcode, operands, '')


arm_arch = ArchConfig(
    name='arm',
    target='armv7-unknown-linux-gnueabi',
    asm='/usr/bin/arm-linux-gnueabi-as',
    objdump='/usr/bin/arm-linux-gnueabi-objdump',
    include='/usr/arm-linux-gnueabi/include',
    asm_line_resolver=resolve_arm_asm_inst,
    objdump_para='-M reg-names-raw',
    as_para='-march=armv7a',
)

x86_arch = ArchConfig(
    name='x86',
    target='i686-unknown-linux-gnu',
    asm='/usr/bin/i686-linux-gnu-as',
    objdump='/usr/bin/objdump',
    include='/usr/i686-linux-gnu/include',
    asm_line_resolver=resolve_x86_asm_inst,
    objdump_para='-M suffix',
    as_para='',
)

# arm64_arch = ArchConfig(
#     name='aarch64',
#     target='aarch64-unknown-linux-gnu',
#     asm='/usr/bin/aarch64-linux-gnu-as',
#     objdump='/usr/bin/aarch64-linux-gnu-objdump',
#     include='aarch64-linux-gnu',
# )
#
#
# x86_64_arch = ArchConfig(
#     name='x86_64',
#     target='x86_64-unknown-linux-gnu',
#     asm='/usr/bin/x86_64-linux-gnu-as',
#     objdump='/usr/bin/x86_64-linux-gnu-objdump',
#     include='/usr/x86_64-linux-gnu32/include',
# )
#
# riscv64_arch = ArchConfig(
#     name='riscv64',
#     target='riscv64-unknown-linux-gnu',
#     asm='/usr/bin/riscv64-linux-gnu-as',
#     objdump='/usr/bin/riscv64-linux-gnu-objdump',
#     include='/usr/riscv64-linux-gnu/include',
# )

archs = [arm_arch, x86_arch]

CLANG_PATH = os.environ.get('CLANG_PATH', None)
LLC_PATH = os.environ.get('LLC_PATH', None)
OPT_PATH = os.environ.get('OPT_PATH', None)

if CLANG_PATH is None:
    raise FileNotFoundError('Could not find clang')
if LLC_PATH is None:
    raise FileNotFoundError('Could not find llc')
if OPT_PATH is None:
    raise FileNotFoundError('Could not find opt')
