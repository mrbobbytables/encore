from flask import Blueprint, Response, json, render_template, current_app, request, send_file
from flask_login import current_user, login_required
from user import User
from job import Job 
from auth import check_view_job, check_edit_job, can_user_edit_job, check_edit_pheno
from genotype import Genotype
from phenotype import Phenotype
from slurm_queue import SlurmJob, get_queue
from model_factory import ModelFactory
import re
import gzip
import tabix
import collections
import numpy as np

api = Blueprint("api", __name__)

@api.before_request
@login_required
def before_request():
    # Just here to trigger the login_required before any request
    pass

@api.route("/genos", methods=["GET"])
def get_genotypes():
    genos = Genotype.list_all()
    def get_stats(x):
        s = Genotype.get(x["id"],current_app.config).get_stats() 
        s["name"] = x["name"]
        s["creation_date"] = x["creation_date"]
        s["build"] = x["build"]
        s["id"] = x["id"]
        return s
    stats = [get_stats(x) for x in genos]
    return json_resp(stats)

@api.route("/genos/<geno_id>", methods=["GET"])
def get_genotype(geno_id):
    g = Genotype.get(geno_id, current_app.config)
    return json_resp(g.as_object())

@api.route("/genos/<geno_id>/info", methods=["GET"])
def get_genotype_info_stats(geno_id):
    g = Genotype.get(geno_id, current_app.config)
    return json_resp(g.get_info_stats())

@api.route("jobs", methods=["POST"])
def create_new_job():
    user = current_user
    if not user.can_analyze:
        return "User Action Not Allowed", 403
    job_desc = dict()
    if request.method != 'POST':
        return json_resp({"error": "NOT A POST REQUEST"}), 405
    form_data = request.form
    genotype_id = form_data["genotype"]
    phenotype_id = form_data["phenotype"]
    job_desc["genotype"] = genotype_id
    job_desc["phenotype"] = phenotype_id
    job_desc["name"] = form_data["job_name"]
    job_desc["response"] =  form_data["response"] 
    if form_data.get("response_invnorm", False):
        job_desc["response_invnorm"] = True
    job_desc["covariates"] =  form_data.getlist("covariates")
    job_desc["genopheno"] =  form_data.getlist("genopheno")
    job_desc["type"] = form_data["model"]
    job_desc["user_id"] = current_user.rid
    job_id = str(uuid.uuid4())

    if not job_id:
        return json_resp({"error": "COULD NOT GENERATE JOB ID"}), 500
    job_directory =  os.path.join(current_app.config.get("JOB_DATA_FOLDER", "./"), job_id)

    job = SlurmJob(job_id, job_directory, current_app.config) 

    try:
        os.mkdir(job_directory)
        job_desc_file = os.path.join(job_directory, "job.json")
        with open(job_desc_file, "w") as outfile:
            json.dump(job_desc, outfile)
    except Exception:
        return json_resp({"error": "COULD NOT SAVE JOB DESCRIPTION"}), 500
    # file has been saved to disc
    try:
        job.submit_job(job_desc)
    except Exception as e:
        print e
        traceback.print_exc(file=sys.stdout)
        shutil.rmtree(job_directory)
        return json_resp({"error": "COULD NOT ADD JOB TO QUEUE"}), 500 
    # job submitted to queue
    try:
        db = sql_pool.get_conn()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO jobs (id, name, user_id, geno_id, pheno_id, status_id)
            VALUES (uuid_to_bin(%s), %s, %s, uuid_to_bin(%s), uuid_to_bin(%s),
            (SELECT id FROM statuses WHERE name = 'queued'))
            """, (job_id, job_desc["name"], job_desc["user_id"], job_desc["genotype"], job_desc["phenotype"]))
        cur.execute("""
            INSERT INTO job_users(job_id, user_id, created_by, role_id)
            VALUES (uuid_to_bin(%s), %s, %s, (SELECT id FROM job_user_roles WHERE role_name = 'owner'))
            """, (job_id, job_desc["user_id"], job_desc["user_id"]))
        db.commit()
    except:
        shutil.rmtree(job_directory)
        return json_resp({"error": "COULD NOT SAVE TO DATABASE"}), 500 
    # everything worked
    return json_resp({"id": job_id, "url_job": url_for("get_job", job_id=job_id)})

@api.route("/jobs", methods=["GET"])
def get_jobs():
    jobs = Job.list_all_for_user(current_user.rid, current_app.config)
    return json_resp(jobs)

@api.route("/jobs/<job_id>", methods=["GET"])
@check_view_job
def get_job(job_id, job=None):
    return json_resp(job.as_object())

@api.route("/jobs/<job_id>", methods=["DELETE"])
@check_edit_job
def retire_job(job_id, job=None):
    result = Job.retire(job_id, current_app.config)
    if result["found"]:
        return json_resp(result)
    else:
        return json_resp(result), 404

@api.route("/jobs/<job_id>", methods=["POST"])
@check_edit_job
def update_job(job_id, job=None):
    result = Job.update(job_id, request.values)
    if result.get("updated", False):
        return json_resp(result)
    else:
        return json_resp(result), 450

@api.route("/jobs/<job_id>/share", methods=["POST"])
@check_edit_job
def share_job(job_id, job=None):
    form_data = request.form
    add = form_data["add"].split(",") 
    drop = form_data["drop"].split(",") 
    for address in (x for x in add if len(x)>0):
        Job.share_add_email(job_id, address, current_user)
    for address in (x for x in drop if len(x)>0):
        Job.share_drop_email(job_id, address, current_user)
    return json_resp({"id": job_id, "url_job": url_for("get_job", job_id=job_id)})

@api.route("/jobs/<job_id>/resubmit", methods=["POST"])
@check_edit_job
def resubmit_job(job_id, Job=None):
    sjob = SlurmJob(job_id, job.root_path, current_app.config) 
    try:
        sjob.resubmit()
    except Exception as exception:
        print exception
        raise Exception("Could not resubmit job ({})".format(exception));
    try:
        db = sql_pool.get_conn()
        cur = db.cursor()
        cur.execute("""
            UPDATE jobs SET status_id = (SELECT id FROM statuses WHERE name = 'queued'), error_message=""
            WHERE id = uuid_to_bin(%s)
            """, (job_id, ))
        db.commit()
    except:
        raise Exception("Could not update job status");
    return json_resp({"id": job_id, "url_job": url_for("get_job", job_id=job_id)})
    return job_handlers.resubmit_job(job_id)

@api.route("/jobs/<job_id>/cancel_request", methods=["POST"])
@check_edit_job
def cancel_job(job_id, Job=None):
    if job is None:
        return json_resp({"error": "JOB NOT FOUND"}), 404
    else:
        slurmjob = SlurmJob(job_id, job.root_path, current_app.config) 
        try:
            slurmjob.cancel_job()
        except Exception as exception:
            print exception
            return json_resp({"error": "COULD NOT CANCEL JOB"}), 500 
    return json_resp({"message": "Job canceled"})

def get_job_output(job, filename, as_attach=False, mimetype=None, tail=None, head=None):
    try:
        output_file = job.relative_path(filename)
        if tail or head:
            if tail and head:
                return "Cannot specify tail AND head", 500
            cmd = "head" if head else "tail"
            count = tail or head
            p = subprocess.Popen([cmd, "-n", count, output_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            tail_data, tail_error = p.communicate()
            resp = make_response(tail_data)
            if as_attach:
                resp.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
            if mimetype:
                resp.headers["Content-Type"] = mimetype
            return resp
        else:
            return send_file(output_file, as_attachment=as_attach, mimetype=mimetype)
    except Exception as e:
        print e
        return "File Not Found", 404

@api.route("/jobs/<job_id>/tables/top", methods=["GET"])
@check_edit_job
def get_job_tophits(job_id, job=None):
    return get_job_output(job, "tophits.json", False)

@api.route("/jobs/<job_id>/plots/qq", methods=["GET"])
@check_view_job
def get_api_job_qq(job_id, job=None):
    return get_job_output(job, "qq.json")

@api.route("/jobs/<job_id>/plots/manhattan", methods=["GET"])
@check_view_job
def get_api_job_manhattan(job_id, job=None):
    return get_job_output(job, "manhattan.json")

@api.route("/jobs/<job_id>/plots/zoom", methods=["GET"])
@check_view_job
def get_job_zoom(job_id, job=None):
    header = []
    output_filename = job.get_output_file_path()
    with gzip.open(output_filename) as f:
        header = f.readline().rstrip('\n').split('\t')
        if header[1] == "BEG":
            header[1] = "BEGIN"
        if header[1] == "POS":
            header[1] = "BEGIN"
        if header[0] == "#CHROM":
            header[0] = "CHROM"
        if header[0] == "CHR":
            header[0] = "CHROM"
        if len(header)>6 and header[6] == "AF_Allele2":
            header[6] = "MAF"
        if len(header)>7 and header[7] == "N":
            header[7] = "NS"
        if len(header)>11 and header[11] == "p.value":
            header[11] = "PVALUE"
    assert len(header) > 0
    chrom = request.args.get("chrom", "")
    start_pos = int(request.args.get("start_pos", "0"))
    end_pos = int(request.args.get("end_pos", "0"))

    if chrom == "":
        return json_resp({"header": {"variant_columns": header}})

    headerpos = {x:i for i,x in enumerate(header)}
    tb = tabix.open(output_filename)
    try:
        results = tb.query(chrom, start_pos, end_pos)
    except:
        if chrom.startswith("chr"):
            chrom = chrom.replace("chr","")
        else:
            chrom = "chr" + chrom
        print [chrom, start_pos, end_pos]
        results = tb.query(chrom, start_pos, end_pos)

    json_response_data = dict()

    json_response_data["CHROM"] = []
    json_response_data["BEGIN"] = []
    json_response_data["MARKER_ID"] = []
    json_response_data["PVALUE"] = []
    if "END" in headerpos:
        json_response_data["END"] = []
    if "NS" in headerpos:
        json_response_data["NS"] = []
    if "MAF" in headerpos:
        json_response_data["MAF"] = []
    if "BETA" in headerpos:
        json_response_data["BETA"] = []
    for r in results:
        if r[headerpos["PVALUE"]] != "NA":
            json_response_data["CHROM"].append(r[headerpos["CHROM"]])
            json_response_data["BEGIN"].append(r[headerpos["BEGIN"]])
            if "END" in headerpos:
                json_response_data["END"].append(r[headerpos["END"]])
            if "MARKER_ID" in headerpos:
                json_response_data["MARKER_ID"].append(r[headerpos["MARKER_ID"]])
            else:
                var1 = "{}:{}".format(r[headerpos["CHROM"]], r[headerpos["BEGIN"]])
                if "Allele1" in headerpos and "Allele2" in headerpos:
                    var1 = "{}_{}/{}".format(var1, r[headerpos["Allele1"]], r[headerpos["Allele2"]])
                json_response_data["MARKER_ID"].append(var1)
            json_response_data["PVALUE"].append(r[headerpos["PVALUE"]])
            if "NS" in headerpos:
                json_response_data["NS"].append(r[headerpos["NS"]])
            if "MAF" in headerpos:
                maf = float(r[headerpos["MAF"]])
                if maf > .5:
                    maf = 1-maf
                json_response_data["MAF"].append(str(maf))
            if "BETA" in headerpos:
                json_response_data["BETA"].append(r[headerpos["BETA"]])
    return json_resp({"header": {"variant_columns": json_response_data.keys()}, \
        "data": json_response_data})

def merge_info_stats(info, info_stats):
    info_extract = re.compile(r'([A-Z0-9_]+)(?:=([^;]+))?(?:;|$)')
    matches = info_extract.findall(info)
    merged = dict()
    if "fields" in info_stats:
        merged[".fieldorder"] = info_stats["fields"]
    for match in matches:
        field = match[0]
        value = match[1]
        if "desc" in info_stats and field in info_stats["desc"]:
            stats = dict(info_stats["desc"][field])
        else:
            stats = dict()
        stats["value"] = value
        merged[field] = stats
    return merged

@api.route("/jobs/<job_id>/plots/pheno", methods=["GET"])
@check_view_job
def get_job_variant_pheno(job_id, job=None):
    chrom = request.args.get("chrom", None)
    pos = request.args.get("pos", None)
    variant_id = request.args.get("variant_id", None)
    if (chrom is None or pos is None):
        return json_resp({"error": "MISSING REQUIRED PARAMETER (chrom, pos)"}), 405
    pos = int(pos)
    geno = Genotype.get(job.meta["genotype"], current_app.config)
    reader = geno.get_geno_reader(current_app.config)
    try:
        variant = reader.get_variant(chrom, pos, variant_id)
    except Exception as e:
        return json_resp({"error": "Unable to retrieve genotypes ({})".format(e)})
    info_stats = geno.get_info_stats()
    info = variant["INFO"]
    calls = variant["GENOS"]
    del variant["GENOS"]
    variant["INFO"] = merge_info_stats(info, info_stats)
    phenos = job.get_adjusted_phenotypes()
    call_pheno = collections.defaultdict(list) 
    for sample, value in phenos.iteritems():
        sample_geno = calls[sample]
        call_pheno[sample_geno].append(value)
    summary = {}
    for genotype, observations in call_pheno.iteritems():
        obs_array = np.array(observations)
        q1 = np.percentile(obs_array, 25)
        q3 = np.percentile(obs_array, 75)
        iqr = (q3-q1)*1.5
        outliers = [x for x in obs_array if x<q1-iqr or x>q3+iqr]
        upper_whisker = obs_array[obs_array<=q3+iqr].max()
        lower_whisker = obs_array[obs_array>=q1-iqr].min()
        summary[genotype] = {
            "min": np.amin(obs_array),
            "w1": lower_whisker,
            "q1": q1,
            "mean": obs_array.mean(),
            "q2": np.percentile(obs_array, 50),
            "q3": q3,
            "w3": upper_whisker,
            "max": np.amax(obs_array),
            "n":  obs_array.size,
            "outliers": outliers
        }
    return json_resp({"header": variant,
        "data": summary})

@api.route("/jobs/<job_id>/progress", methods=["GET"])
@check_view_job
def get_job_progress(job_id, job=None):
    sej = SlurmJob(job_id, job.root_path, current_app.config)
    return json_resp(sej.get_progress())

@api.route("/queue", methods=["GET"])
@api.route("/queue/<job_id>", methods=["GET"])
def get_queue_status(job_id=None):
    queue = get_queue()
    summary = {"running": len(queue["running"]),
        "queued": len(queue["queued"])}
    if job_id is not None:
        try:
            position = [x["job_name"] for x in queue["queued"]].index(job_id) + 1
            summary["position"] = position
        except:
            pass
    return json_resp(summary) 

@api.route("/phenos", methods=["GET"])
def get_phenotypes():
    phenos = Phenotype.list_all_for_user(current_user.rid)
    return json_resp(phenos)

@api.route("/phenos/<pheno_id>", methods=["GET"])
def get_pheno(pheno_id):
    p = Phenotype.get(pheno_id, current_app.config)
    return json_resp(p.as_object())

@api.route("/phenos/<pheno_id>", methods=["POST"])
@check_edit_pheno
def update_pheno(pheno_id, pheno=None):
    result = Phenotype.update(pheno_id, request.values)
    if result.get("updated", False):
        return json_resp(result)
    else:
        return json_resp(result), 450

@api.route("/phenos/<pheno_id>", methods=["DELETE"])
@check_edit_pheno
def retire_pheno(pheno_id, pheno=None):
    result = Phenotype.retire(pheno_id, current_app.config)
    if result["found"]:
        return json_resp(result)
    else:
        return json_resp(result), 404

@api.route("/phenos", methods=["POST"])
def post_api_pheno():
    return pheno_handlers.post_to_pheno()

@api.route("/models", methods=["GET"])
@login_required
def get_models():
    models = ModelFactory.list(current_app.config)
    return json_resp(models)

def json_resp(data):
    resp = Response(mimetype='application/json')
    resp.set_data(json.dumps(data))
    return resp

