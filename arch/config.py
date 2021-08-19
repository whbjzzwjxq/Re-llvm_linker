import os
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ArchConfig:
    name: str
    target: str
    asm: str
    objdump: str
    include: str

    @property
    def bc_file(self):
        return self.name + '_bc'

    @property
    def ir_file(self):
        return self.name + '_ir'

    @property
    def asm_file(self):
        return self.bc_file + '.s'

    @property
    def asm_dump_file(self):
        return self.bc_file + '_dump.s'

    @property
    def obj_file(self):
        return self.bc_file + '.o'

    @property
    def stdout_file(self):
        return self.name + '.tmp'

    @property
    def files(self):
        return [
            self.bc_file,
            self.ir_file,
            self.asm_file,
            self.asm_dump_file,
            self.obj_file,
        ]

    def gen_file_rela_paths(self, temp_dir: str) -> Tuple[str, ...]:
        bc_file = os.path.join(temp_dir, self.bc_file)
        ir_file = os.path.join(temp_dir, self.ir_file)
        asm_file = os.path.join(temp_dir, self.asm_file)
        asm_dump_file = os.path.join(temp_dir, self.asm_dump_file)
        obj_file = os.path.join(temp_dir, self.obj_file)
        stdout_file = os.path.join(temp_dir, self.stdout_file)
        return bc_file, ir_file, asm_file, asm_dump_file, obj_file, stdout_file


arm_arch = ArchConfig(
    name='arm',
    target='armv6a-unknown-linux-gnueabi',
    asm='/usr/bin/arm-linux-gnueabi-as',
    objdump='/usr/bin/arm-linux-gnueabi-objdump',
    include='/usr/arm-linux-gnueabi/include',
)

arm64_arch = ArchConfig(
    name='aarch64',
    target='aarch64-unknown-linux-gnu',
    asm='/usr/bin/aarch64-linux-gnu-as',
    objdump='/usr/bin/aarch64-linux-gnu-objdump',
    include='aarch64-linux-gnu',
)

x86_arch = ArchConfig(
    name='x86',
    target='i686-unknown-linux-gnu',
    asm='/usr/bin/i686-linux-gnu-as',
    objdump='/usr/bin/i686-linux-gnu-objdump',
    include='/usr/i686-linux-gnu/include',
)

x86_64_arch = ArchConfig(
    name='x86_64',
    target='x86_64-unknown-linux-gnu',
    asm='/usr/bin/x86_64-linux-gnu-as',
    objdump='/usr/bin/x86_64-linux-gnu-objdump',
    include='/usr/x86_64-linux-gnu32/include',
)

riscv64_arch = ArchConfig(
    name='riscv64',
    target='riscv64-unknown-linux-gnu',
    asm='/usr/bin/riscv64-linux-gnu-as',
    objdump='/usr/bin/riscv64-linux-gnu-objdump',
    include='/usr/riscv64-linux-gnu/include',
)

archs = [arm_arch, arm64_arch, x86_arch, x86_64_arch]

CLANG_PATH = os.environ.get('CLANG_PATH', None)
LLC_PATH = os.environ.get('LLC_PATH', None)

if CLANG_PATH is None:
    raise FileNotFoundError('Could not find clang')
if LLC_PATH is None:
    raise FileNotFoundError('Could not find llc')
