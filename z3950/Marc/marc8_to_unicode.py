import sys
import unicodedata

from z3950.Marc import marc8_mapping


def marc8_to_unicode(marc8) -> str:
    converter = MARC8ToUnicode()
    try:
        return converter.translate(marc8)
    except IndexError:
        # convert IndexError into UnicodeDecodeErrors
        raise UnicodeDecodeError("marc8_to_unicode", marc8, 0, len(marc8), "invalid multibyte character encoding",)
    except TypeError:
        raise UnicodeDecodeError("marc8_to_unicode", marc8, 0, len(marc8), "invalid multibyte character encoding",)


class MARC8ToUnicode:
    basic_latin = 0x42
    ansel = 0x45

    def __init__(self, G0: int = basic_latin, G1: int = ansel) -> None:
        self.g0 = G0
        self.g0_set = {b"(", b",", b"$"}
        self.g1 = G1
        self.g1_set = {b")", b"-", b"$"}

    def translate(self, marc8_string):
        if not marc8_string:
            return ""
        uni_list = []
        combinings = []
        pos = 0
        while pos < len(marc8_string):
            if marc8_string[pos : pos + 1] == b"\x1b":
                next_byte = marc8_string[pos + 1 : pos + 2]
                if next_byte in self.g0_set:
                    if len(marc8_string) >= pos + 3:
                        if (
                            marc8_string[pos + 2 : pos + 3] == b","
                            and next_byte == b"$"
                        ):
                            pos += 1
                        self.g0 = ord(marc8_string[pos + 2 : pos + 3])
                        pos = pos + 3
                        continue
                    else:
                        uni_list.append(marc8_string[pos : pos + 1].decode("ascii"))
                        pos += 1
                        continue

                elif next_byte in self.g1_set:
                    if marc8_string[pos + 2 : pos + 3] == b"-" and next_byte == b"$":
                        pos += 1
                    self.g1 = ord(marc8_string[pos + 2 : pos + 3])
                    pos = pos + 3
                    continue
                else:
                    charset = ord(next_byte)
                    if charset in marc8_mapping.CODESETS:
                        self.g0 = charset
                        pos += 2
                    elif charset == 0x73:
                        self.g0 = self.basic_latin
                        pos += 2
                        if pos == len(marc8_string):
                            break

            def is_multibyte(charset):
                return charset == 0x31

            mb_flag = is_multibyte(self.g0)

            if mb_flag:
                code_point = (
                    ord(marc8_string[pos : pos + 1]) * 65536
                    + ord(marc8_string[pos + 1 : pos + 2]) * 256
                    + ord(marc8_string[pos + 2 : pos + 3])
                )
                pos += 3
            else:
                code_point = ord(marc8_string[pos : pos + 1])
                pos += 1

            if code_point < 0x20 or 0x80 < code_point < 0xA0:
                uni = chr(code_point)
                continue

            try:
                if code_point > 0x80 and not mb_flag:
                    (uni, cflag) = marc8_mapping.CODESETS[self.g1][code_point]
                else:
                    (uni, cflag) = marc8_mapping.CODESETS[self.g0][code_point]
            except KeyError:
                try:
                    uni = marc8_mapping.ODD_MAP[code_point]
                    uni_list.append(chr(uni))
                    continue
                except KeyError:
                    pass
                sys.stderr.write("Unable to parse character 0x%x in g0=%s g1=%s\n" % (code_point, self.g0, self.g1))
                uni = ord(" ")
                cflag = False

            if cflag:
                combinings.append(chr(uni))
            else:
                uni_list.append(chr(uni))
                if len(combinings) > 0:
                    uni_list.extend(combinings)
                    combinings = []

        uni_str = "".join(uni_list)
        return unicodedata.normalize("NFC", uni_str)
