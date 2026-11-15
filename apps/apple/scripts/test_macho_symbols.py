import struct
import unittest

from macho_symbols import symbol_tables


def binary(cpu=0x100000c, entries=(("_PLStart", 0x0f),)):
    names, records = b"\0", b""
    for name, kind in entries:
        records += struct.pack("<IBBHQ", len(names), kind, 1, 0, 0x1000)
        names += name.encode() + b"\0"
    header = struct.pack("<IIIIIIII", 0xfeedfacf, cpu, 0, 2, 1, 24, 0, 0)
    command = struct.pack("<IIIIII", 2, 24, 56, len(entries), 56 + len(records), len(names))
    return header + command + records + names


class SymbolTablesTest(unittest.TestCase):
    def test_defined_exports_exclude_imports(self):
        value, = symbol_tables(binary(entries=(("_PLStart", 0x0f), ("_malloc", 1))))
        self.assertEqual(value["external"], {"_PLStart"})
        self.assertEqual(value["local"], [])
        self.assertEqual(value["debug"], 0)

    def test_local_and_debug_symbols_cannot_be_mistaken_for_exports(self):
        value, = symbol_tables(binary(entries=(("local", 0x0e), ("debug", 0x24))))
        self.assertEqual(value["external"], set())
        self.assertEqual(value["local"], ["local"])
        self.assertEqual(value["debug"], 1)

    def test_every_universal_architecture_is_inspected(self):
        first, second = binary(), binary(0x1000007, (("unstripped", 0x0e),))
        fat = struct.pack(">II", 0xcafebabe, 2)
        fat += struct.pack(">IIIII", 0x100000c, 0, 48, len(first), 0)
        fat += struct.pack(">IIIII", 0x1000007, 0, 48 + len(first), len(second), 0)
        values = symbol_tables(fat + first + second)
        self.assertEqual([value["cpu"] for value in values], [0x100000c, 0x1000007])
        self.assertEqual(values[1]["local"], ["unstripped"])
        with self.assertRaises(ValueError):
            symbol_tables(fat + first + second[:-1])

    def test_missing_and_truncated_tables_fail_closed(self):
        for data in (b"not Mach-O", binary()[:-1], binary()[:32], binary()[:16]):
            with self.assertRaises((ValueError, struct.error)):
                symbol_tables(data)


if __name__ == "__main__":
    unittest.main()
