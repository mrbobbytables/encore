import subprocess
import re
import csv
from collections import defaultdict, Counter

# These three functions
# guess_raw_type, guess_atomic_column_class, guess_column class
# attempt to identify the type of variable in each of the columns
# of a phenotype file

def guess_raw_type(s):
    if re.match(r'^\s*$', s):
        return "_empty_"
    try:
        f = float(s)
        if "." not in s:
            return "int"
        return "float"
    except ValueError:
        value = s.upper()
        if value =="TRUE" or value == "FALSE":
            return "bool"
        return type(s).__name__

def guess_atomic_column_class(rawtype, obs):
    n_vals = sum(obs.values())
    n_uniq_vals = len(obs)
    if n_vals == n_uniq_vals and rawtype != "float":
        return {"class": "id", "type": rawtype}
    if n_uniq_vals == 1:
        return {"class": "fixed", "type": rawtype, "value": obs.keys()[0]}
    if n_uniq_vals == 2:
        return {"class": "binary", "type": rawtype, "levels": obs.keys()}
    if rawtype == "str":
        if float(n_uniq_vals)/n_vals > .75:
            return {"class": "descr", "type": "str"}
        else:
            return {"class": "categorical", "type":"str", "levels": obs.keys()}
    if rawtype == "float" or rawtype == "int":
        return {"class": "numeric", "type": rawtype}
    return {"class": rawtype, "type": rawtype}

def guess_column_class(colinfo):
    # colinfo is dict (types) of counters (values)
    has_empty = "_empty_" in colinfo
    col = {k: v for k,v in colinfo.iteritems() if k != "_empty_"}
    n_vals = Counter({k: sum(v.values()) for k, v in col.iteritems()})
    n_uniq_vals = Counter({k: len(v) for k, v in col.iteritems()})
    if len(col)==0:
        #all empty
        return {"class": "fixed", "type": "str"}
    if len(col)==1:
        # all same type
        best_type = n_vals.most_common(1)[0][0]
        return guess_atomic_column_class(best_type, col[best_type])
    if len(col)==2 and "int" in col and "float" in col:
        #promote to float
        best_type = "float"
        vals = col["int"] + col["float"]
        return guess_atomic_column_class(best_type, vals)
    if len(col)==2 and (n_uniq_vals["str"]==1):
        # likely a numeric value with a missing indicator
        best_type = [x[0] for x in n_vals.most_common(2) if x[0] != "str"][0]
        ci = guess_atomic_column_class(best_type, colinfo[best_type])
        ci["missing"] = colinfo["str"].keys()[0]
        return ci
    return None

def strip_comments(item, token="#"):
    for line in item:
        s = line.strip()
        if not s.startswith(token):
            yield s

def get_comments(item, token="#"):
    for line in item:
        s = line.strip()
        if not s.startswith(token) and len(s)>0:
            raise StopIteration
        yield s

def sniff_file(csvfile):
    chunk = "\n".join([x for _,x in zip(range(50), strip_comments(csvfile))])
    try:
        return csv.Sniffer().sniff(chunk, "\t|, ")
    except:
        return None

def find_header(firstrow, lastcomment, cols):
    colclasses = {k: guess_column_class(v) for k,v in cols.items()}
    firstrowtypes = [guess_raw_type(x) for x in firstrow]
    coltypes = [z["type"] for z in [colclasses[i] for i in xrange(len(firstrow))]]
    rowtypes = [guess_raw_type(x) for x in firstrow]
    if sum([x=="str" for x in firstrowtypes]) > sum([x=="str" for x in coltypes]):
        # we have more strings than expected, assume it's the header
        return (firstrow, "firstrow")
    if len(lastcomment) == len(colclasses):
        # we have a length match of mostly str values, assume it's the header
        commenttypes = [guess_raw_type(x) for x in lastcomment]
        if sum([x=="str" for x in commenttypes])/float(len(commenttypes)) > .9:
            return (lastcomment, "comment")
    # no header found, return unique names
    return (["COL{0}".format(i) for i in xrange(len(colclasses))], "position")

def check_if_ped(cols, obs):
    if len(cols)<6:
        return False, None
    types = [x["type"] for x in cols]
    classes = [x["class"] for x in cols]
    if not (classes[0] == "id" or classes[1]=="id"):
        return False, None
    if not (types[2] == types[1] or classes[2]=="fixed"):
        return False, None
    if not (types[3] == types[1] or classes[3]=="fixed"):
        return False, None
    if not (classes[4]=="binary" or classes[4]=="fixed"):
        return False, None
    return True, None 

def infer_meta(csvfile, dialect=None):
    meta = {"layout": {}, "columns": []}

    # store csv dialect
    if not dialect:
        csvfile.seek(0)
        dialect = sniff_file(csvfile)
    for k in [k for k in dir(dialect) if not k.startswith("_")]:
        meta["layout"]["csv_" + k] = getattr(dialect, k)

    # read comments 
    csvfile.seek(0)
    comments = list(get_comments(csvfile))

    # read and process csv rows 
    csvfile.seek(0)
    cvr = csv.reader(strip_comments(csvfile), dialect)
    firstrow = next(cvr)
    cols = defaultdict(lambda : defaultdict(Counter))
    for row in cvr:
        for idx, val in enumerate(row):
            cols[idx][guess_raw_type(val)][val] += 1
    # find column headers
    if comments:
        lastcomment = next(csv.reader([comments[-1][1:]], dialect))
    else:
        lastcomment = None
    headers, headersource = find_header(firstrow, lastcomment, cols)
    if headersource == "position":
        skip = len(comments)+1
    else:
        skip = len(comments)
    meta["layout"]["skip"] = skip
    # define columns
    meta["columns"] = [None] * len(cols)
    for col, colval in cols.items():
        coldef = guess_column_class(colval)
        coldef["name"] = headers[col]
        meta["columns"][col] = coldef
    #check if ped
    pedlike, ped_columns = check_if_ped(meta["columns"], cols)
    if pedlike:
        colclasses = ["family_id","sample_id","father_id","mother_id","sex"]
        for actas, col in zip(colclasses, meta["columns"][0:3]):
            if col["class"] != "fixed":
                col["class"] =  actas
    return meta

class PhenoReader:
    def __init__(self, path, meta=None):
        self.path = path
        if meta:
            self.meta = meta
        else:
            self.meta = self.infer_meta()

    def infer_meta(self):
        with open(self.path, 'rb') as csvfile:
            return infer_meta(csvfile)

    def get_dialect(self, opts=None):
        class dialect(csv.Dialect):
            pass
        if opts is None and self.meta and self.meta["layout"]:
            opts = {k[4:]:v for (k,v) in self.meta["layout"].items() if k.startswith("csv_")}
            opts = {k: v.encode('utf8') if isinstance(v, unicode) else v
                for (k,v) in opts.items()} 
        for (k, v) in opts.items():
            setattr(dialect, k, v)
        return dialect

    def get_column_indexes(self):
        cols = self.get_columns();
        return { v["name"]: i for (i,v) in enumerate(cols)}

    def get_columns(self):
        if self.meta and self.meta["columns"]:
            return self.meta["columns"]
        else:
            return [];

    def data_extractor(self, cols):
        pos = self.get_column_indexes()
        missing = [c for c in cols if not c in pos];
        if len(missing)>0:
            raise ValueError("can't find columns: " + ", ".join(missing))
        extract = [pos[c] for c in cols]
        dialect = self.get_dialect()
        skip = self.meta['layout']['skip']
        with open(self.path, 'rb') as csvfile:
            if skip>0:
                [csvfile.readline() for i in xrange(skip)]
            cvr = csv.reader(csvfile, dialect)
            for row in cvr:
                yield [row[i] for i in extract]

    @staticmethod
    def get_file_type(file):
        p = subprocess.Popen(["file", "-b", file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        human, err = p.communicate()
        p = subprocess.Popen(["file","-b","-i", file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        mime, err = p.communicate()
        return human.rstrip(), mime.rstrip()

    @staticmethod
    def is_text_file(file):
        human, mime = PhenoReader.get_file_type(file)
        istext = re.search(r"\btext\b", human) is not None
        return istext, human, mime  

if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv)>=2:
        meta = None
        if len(sys.argv)>=3:
            with open(sys.argv[2]) as f:
                meta = json.load(f)
            p = PhenoReader(sys.argv[1], meta)
            print [x for x in p.data_extractor(["VAL", "COL"])]
        else:
            p = PhenoReader(sys.argv[1], meta)
            print json.dumps(p.meta, indent=2)

