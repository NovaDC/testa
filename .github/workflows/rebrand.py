from functools import cache
from itertools import chain
from os import renames
from pathlib import Path
from shutil import move
from typing import Dict, Iterable, Set, Union, Tuple, Optional, List
from warnings import warn
from tqdm import tqdm as TQDM
from re import Pattern, compile

SELF_EXPECTED_REPO_PATH: Path = Path("./.githubworkflows/rebrand.py")

COMMON_READ_ERRORS = (
    ValueError,
    TypeError,
    UnicodeError,
    PermissionError,
    FileNotFoundError,
)


@cache
def this_path() -> Path:
    this = SELF_EXPECTED_REPO_PATH
    if "__file__" in globals().keys():
        file_path = Path(__file__)
        if file_path.exists():
            this = file_path
    return this

@cache
def path_safeify(repl: str, allow_spaces: bool = True) -> str:
    return "".join(c if (c.isalnum() or c in (".", "_") or (allow_spaces and c == " ")) else "_" for c in repl.strip())
# TODO just do multiple replacment in one go, make path safe things obsolitete maybe?


def rebrand(
    replacment_mapping: Dict[Union[str, Pattern],
                             Union[str, Tuple[Optional[str], Optional[str]]]] = {},
    filename_pattern_blacklist: Iterable[Union[str, Path]] = tuple(),
    tqdm: Optional[TQDM] = None,
    *,
    repo_root: Path = Path.cwd(),
    encoding: Optional[str] = "utf-8",
    errors: Optional[str] = None,
):
    filename_pattern_blacklist = set(chain.from_iterable(repo_root.rglob(bl if isinstance(bl, str) else str(bl.absolute())) for bl in filename_pattern_blacklist)) | {this_path()}
    print(filename_pattern_blacklist)

    final_mapping: Dict[Pattern, Tuple[Optional[str], Optional[str]]] = {}

    for patt, repl in replacment_mapping.items():
        patt_str = patt
        if not isinstance(patt, Pattern):
            patt = compile(patt)
        else:
            patt_str = patt.pattern
        if patt_str == "":
            continue
        if not isinstance(repl, tuple):
            repl = (repl,)
        if len(repl) != 2:
            repl = (repl[0], path_safeify(repl[1]) if len(repl) > 1 else None)
        if repl.count(None) < 2 and (repl[0] is not None and patt_str != repl[0]) and (repl[0] is not None and patt_str != repl[1]):
            final_mapping[patt] = repl

    if len(final_mapping) < 1:
        return

    # collect only reasonably possible targets is a way that we can count ho many thier are (not a itnerable, something sized)
    target_files: Set[Path] = set(f for f in repo_root.rglob("*") if f.absolute() not in filename_pattern_blacklist and not any((bl in f.absolute().parents) for bl in filename_pattern_blacklist))

    if tqdm is not None:
        tqdm.total = len(target_files)

    for path in sorted(target_files, key = lambda p: (-len(p.parts), list(p.parts))): #sort to ensure that paths furthest down the tree are renamed first, to avoid renaming a parent of a file that we later want to rename anyway...
        print(path)
        text = None
        text_replaced = False
        if path.is_file():
            try:
                text = path.read_text(encoding, errors)
            except COMMON_READ_ERRORS:
                pass
        out_path = path

        # now do the actual substitution
        for patt, (content_name, path_safe_name) in final_mapping.items():
            if path_safe_name is not None:
                out_path = Path(*(patt.sub(path_safe_name, s)
                                for s in out_path.parts))
            if text is not None and content_name is not None:
                subbed = patt.sub(content_name, text)
                text_replaced = text_replaced or subbed != text
                text = subbed

        if text_replaced and text is not None:  # this implicitly renames the file; text is guaranteed to never be none if text_replaced but type checkers dont recongize this for whatever reason
            if path != out_path:
                # remove a old path if its different from the new path, this is safe since we have the new content in ram
                path.unlink(True)
            #for whatever reeason wt+ refuses to create files i fthey dont exist
            if not out_path.parent.exists():
                out_path.parent.mkdir(parents=True)
            with out_path.open("wt+", encoding=encoding, errors=errors) as f:
                f.write(text)
            if tqdm is not None:
                tqdm.update(1)
        elif path != out_path:
            try:
                move(path, out_path)

            except FileExistsError as e:
                if (not out_path.is_dir()) or (not path.is_dir()):
                    raise e
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink(False)
            if tqdm is not None:
                tqdm.update(1)
        else:  # huh, there was nothing to do on a path... but
            if path.is_file():
                pass
                #warn(
                #    f"File {path.relative_to(repo_root, walk_up=True)} has nothing to do! Is {path.relative_to(repo_root, walk_up=True)} a text file?")
            if tqdm is not None:
                # this was an exception, dont count this file in the total...
                tqdm.total -= 1


def self_destruct():
    this_path().unlink()


VERSION = "v0.1.0.0"

if True: #__name__ == "__main__":
    from sys import argv
    from argparse import ArgumentParser

    REPLACMENT_ARG_PATTERN = compile(r"^ *\"?(?P<PATTERN>.*?)\"? *(?:=r= *\"?(?P<VALUE>.*?)\"? *)?(?:=p= *\"?(?P<SAFEVALUE>.*?)\"? *)?$")

    p = ArgumentParser(argv[0])
    p.add_argument("--version", "-v", action="version", version=VERSION)
    p.add_argument("--selfdestruct", "-d", "--sd", action="store_true")
    p.add_argument(
        "-r", "--replacements", type=str, nargs="*", action="append",
        help="Specify replacements as 'pattern[=r=[\"]replacement[\"][=p=[\"]pathsafereplacement[\"]]', using double quotes (not single quotes) to encapsualte a string that might have character spaces. A replacment with no replacment value or path safe replacment value will be replaced with a empty string (removed). To disable quote parsing, use --no_quote_parsing."
    )
    p.add_argument("-e", "--encoding", type=str,
                   help="encoding to use for reading and writing files", default="utf-8")
    p.add_argument("--blacklist", "-b", type=str, action="append", nargs="*", default = list(),
                   help="add paths to ignore, can be specified multiple times")
    p.add_argument("-t", "--tqdm", action="store_true")
    p.add_argument("--nq", "--no_quote_parsing", action="store_true")
    p.add_argument("-m", "--make_pathsafename", action="store_true",
                   help="automatically make a safe name from the pattern if no safe name is given")
    p.add_argument("--dryrun", "-n", "--nd", "--dr", "--dry", action="store_true",
                   help="just print out the replacment patterns instead of rebranding")

    parsed = p.parse_args(argv[1:])

    blacklist = [" ".join(l) for l in parsed.blacklist]

    final_mapping = {}
    for replacement in parsed.replacements:
        replacement = " ".join(replacement)
        match = REPLACMENT_ARG_PATTERN.match(replacement)
        if match is None:
            continue  # skip invalid entries

        content_name = match.group("VALUE")
        if content_name is not None and len(content_name) < 1:
            content_name = None

        path_safe_name = match.group("SAFEVALUE")
        if path_safe_name is not None and len(path_safe_name) < 1:
            path_safe_name = None

        if content_name is None and path_safe_name is None:
            content_name = ""
        if path_safe_name is None and content_name is not None and parsed.make_pathsafename:
            path_safe_name = content_name
        if path_safe_name is not None:
            path_safe_name = path_safeify(path_safe_name)

        final_mapping[match.group("PATTERN")] = (content_name, path_safe_name)

    if parsed.dryrun:
        print("Replacement patterns:")
        for patt, (content_name, path_safe_name) in final_mapping.items():
            out = f"'{patt}'"
            if content_name is not None and content_name == "":
                content_name = " (an empty string)"
            if content_name is not None:
                out += f" -> '{content_name}'"
            if path_safe_name is not None and path_safe_name == "":
                path_safe_name = " (an empty string)"
            if path_safe_name is not None:
                out += f" ( -> '{path_safe_name}' for paths)"
            print(out)
    else:
        rebrand(
            final_mapping,
            blacklist,
            TQDM() if parsed.tqdm else None,
            repo_root=Path.cwd(),
            encoding=parsed.encoding,
        )

    if parsed.selfdestruct:
        self_destruct()