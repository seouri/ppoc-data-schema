import base64
import copy
import gzip
import json
import math

import pytest

from synthetic.derivation_parity import (
    DerivationImplementation,
    DerivationParityPolicy,
    DerivationParityStatus,
    DerivationParityUnavailable,
    validate_derivation_parity,
)

_DESCRIPTOR = "ABzY8!jzV30{`t?TW{OA68<ZKpSpm($Ci`k@|Gqp8l2{`Nq39IIfXz=V~YqyDx~BjE%M*bP!~tG6`OSAZBOEdHj?;pIQ)i}nIYjHtyqc?WzafoC1jW~B0B*|NGB%#4H-kL-IAb0Dt%C`!~gtfaS~~4OcDw_QCN<TVdcy3zM9}y;JyebA7e?Hj5_=HDWHUbpR^8tv_c>O$kt&ZQ@{dXG@^<AfUtJ!HWdjRheW^sx20=}bjaWj{W-7m*lsC5gotQiBML02)6Sy-R!$yb{Y@oOtJ7}zg5xuxT6?T5;Wnibf<o|Pdn!f2{p#w#(+HbxeZ-<O{P$<;TYHI2NJ371nmm|GJ{O7eiK>`jMMp^IGj@&(#Mgd24uw$QaIBOF=ZLF2q!rcTH(cED?1><ky3iLavq!sine*iY0#sI2gInLKic8{y*E84pC;~}+!ktr&cIR5hBSzE>an7-^i5^%-*is16xkAzURUr=leqcECGW;l)P>NdU9VvTvMuPzRG$0BGQP$SEkXkk`g&-(z*ZD;52rV?a$lAXoJ{=*Ar-~6CWCH66sVDD=+OHuF;u_lAEp6-2*5A^$4sAPI+SZ|McT3wkw7uWbwhnE3TiVv4ZGTIf5pC#$MpP*z=r6+3%yn;R$268SBJ$zi@G$QskAws|=2)V^-_XIn?=Ue&)!E1SqJ=2HBk4H82M8A9fv2)<WbhLsgI~~@Z+z1Hvi|o!*3<r*>FLg!>FMs9>FN77)6=~-)6@O8&{K3;SQ0*XBSywg{l)&lIIB|M;cmOP)FbdiDR2|_g8POAkEOUv!sg||1f-{ul%vNn-h}KsG~$Ltr`o!A=;wyXCd7*&DD>?b7CoUTRC&HY$_=DOl+#EH?wShqVhK1-8k3DEFO%<)F$yLRYEg6*PVQ~sh34A#eFnUy+Bj3R0uMlBMJU>6IIBPv=Rvpc9hjqgU30AKdN%03CHlPuddD2w@7m~r=$-|7r|SC}pe^*?bG@FqDmS}b3#^6Q0~`8yZ{Hm2?pjEWyEatE-CYapo;h~ULgNG1Vo2Za?O9;=Etu12b9>+J?^&W<D|FuqZ9ZLY4=fltu&~R471xN~u|h8$r}<`BxCh@o<qHW`yUWZb2)I8zCu^~7l?1EMrVUe@cJ=0Kj?Nhh8)PW7Vkm5kq0ow<(2}8HM4O?fR!}`R%b*s-7`CWcF@%<bh6J8ZrQg)Jc~;zWLuXY5tI=c8dOm<GD$J}yBOyHoe2k%7lS|Svu}fDcgNpVGm7O+~HOsEz0<kI~Ns7Tw)670AcO|u}YOcqvg+6oSuB`deL#U_on^}~E5lG-Z<cBo*?X=lDX>}DJ9}Q2n@-Xu0BrAV^J*QWBMEx=u+IOPHQTCGL2+w97NH3FNoGZK-ji?XKU%D$gCkKq>FV4GT!6(1}h99q~e}jKM3dY1;=g(N<2)pT=W(T<_H)TowGy$oo;Lf1bMyCYfZYZRNegOs%1k|S-iq|+4+4I+IIylE6WKA72oN_p}oa;1>h1AkdgrDl;PqduS!cL<o<@9^`imf=sS+9OevD-z-nQk$IIcJ0;-%*K?3Y-hh^g-d#P?M9L0)J#F{{I<Y@=8w~{7i;3CDmSDO5sC*)7Y65R9;Hxi1=UnPdqKWkT|Thr3X@C&qb<cq~yh=QiFS)X+;)Lg@nvpFgydL@>`{Y39bnx3#g%UrN@XWdw=Z{&LMD0`ZNd<l<T~^NE2<{D;QD6^25$VNZs&7944VNxF?bREL2Prq7hdjP0)4@_KB1H(-%p&@+BQs`c^7=Ot8mSFrlDN+y^mLA^@~8;bWNPU^*0L*chB>T~c|eEu%;2QGn#;Dt?hblB`2Z6MI6^v4?ZR%NI8fmGHd>ZazQ$)+1#$NnI@6;`_2SzHnzLUk)l=7C%~s`*3!;tXMmVF<|$2qAws@>}PGg7v;~rZg*}y@o+sJ*PL$Gp<E+W-w3s1gxWPiy*EPb8KL%#PzOe+YLapp%#8h>8T~yo{(EKy=$TodXJ&$)nGJeoM(CMY!8NmjYd8nYtl*ki!8NmjYi0%4%nGiV6<jkbxMo)9n^~c6W`(}tQdDCFBR{+1^!-X+cHPaf`I3&?b$5Gi_n^1i#lKree0vq`|M8MQQz26!Cqm~sTzVQ=09T$`8aajq=w@spDNPu~kk0<Fd*;v;SVBCbc5`Tj;G){vS(~EO2{17`51#F_LH?vbHtq7RmG4@tv_Z8ja!fU~8dq#1mq-i)rwp__Y6_d5L`Ll{PNMK-lPENwL~~G+k@8Fx58`!dk+o_ut6EJD<mctrk<fG#Wb;k1W}7e{R83oILwDj#^DtINOi$pZSr|riRXWH(zfEL~v`n9%G4dpxp(|RsGKe59WR#^A#ia68-}}=_Dt!wO%4>kLj^XC69&YB=;WlT#&Dn2r_WwxEew)tTrn9%{>}@)Go6i1e>FjnzVx`sR<V`P+ELK{Y8gI6hDbtJ$D>qs6+hY10_qopg{_a7i_nLC(vm|&zdkimZ3k`tYnTHM|czVyaNR0FzYxM~*=<u3K3~RAd_s`2dt{~+J9f0<%;=+?#TB%@Rwd#w^`67zZ^FpJq(ypXhP+Tf-q?&-WcWQ#0jfPepI1Hze-6sqjv{Re?62moc?fGUW4p$gvsf1)MuLfawfH4KWygR=*A860_yp&OvoNC8YM<_^RE^}JxSjQ87hCYXJd8(1g#Sp54Zgv*;UZ=_jv=~mh&WZj}iW7(dL&;2wQfsHsdHS9!f69?88kD8ibX@q#P8M=qifPwMWt^wZ&uB3%&jlYdqLkA;bTG=%e)$n&AjiO+>llhdlJP)?SUTD0%xhVymCO2&1rJl9?xAyr13@BT&Swm#*$UzFnxAqfi=332itHa|g)78W*g466XJbzLT-{PR_TW^<##e!{pXqOM@RYHic|g0NT_~Ey#g)yd@^O2lJ9}j~z(v-_9ijn28`x*GSX}L-<sP7`;re7>so=sc*_5rXJX=J|+{W_oJ?j;XVg??r0s3UPev?{Bl#%~BZ{t@t<<Ygk=@+51q>{>y0#&}go=IQr)eA*&)I6~EtpuCc){0pcfo*7bFEa9LTsq3+OTsGK(Dc(A*o11BcyUNnh-q|((IuetOi<btBdq2sQk@d{8IUJN-gKR^iO`IO_AGI)WZnMu_&@J&5uFKI000"


def descriptor():
    package = json.loads(gzip.decompress(base64.b85decode(_DESCRIPTOR)))
    next(
        resource
        for resource in package["resources"]
        if resource["name"] == "visits_augmented"
    )["path"] = "visits_augmented.csv"
    return package


def field_specs(package, resource_name):
    return next(item for item in package["resources"] if item["name"] == resource_name)["schema"]["fields"]


def row(package, resource_name, **overrides):
    values = {}
    for spec in field_specs(package, resource_name):
        constraints = spec.get("constraints", {})
        if spec["type"] in {"integer", "number"}:
            value = 0
        elif constraints.get("required") and constraints.get("enum"):
            value = constraints["enum"][0]
        else:
            value = ""
        values[spec["name"]] = value
    values.update(overrides)
    return values


def policy(**overrides):
    values = {
        "policy_id": "parity-policy",
        "policy_version": "v1",
        "minimum_patient_rows": 1,
        "minimum_visit_rows": 1,
        "deterministic_tolerance": 0.001,
        "reference_tolerance": 0.01,
    }
    values.update(overrides)
    return DerivationParityPolicy(**values)


def implementation(name):
    return DerivationImplementation(name, "a" * 64, True)


def fixtures():
    package = descriptor()
    patient = row(
        package,
        "patients",
        patient_id="fictional-person",
        sex="F",
        ethnicity="Choose not to Answer",
        race_1="Unknown",
    )
    visits = [
        row(
            package,
            "visits",
            patient_id="fictional-person",
            visit_id="fictional-visit-one",
            age_in_days=730,
            encounter_type="Office Visit",
            orig_enc_source_Epic_yn="Y",
            weight_oz=70.548,
            height_in=20,
            head_circ_cm=45,
            BMI=17,
            bmi_percentile=50,
            enc_diag_1="E10.9",
        ),
        row(
            package,
            "visits",
            patient_id="fictional-person",
            visit_id="fictional-visit-two",
            age_in_days=800,
            encounter_type="Office Visit",
            orig_enc_source_Epic_yn="Y",
            weight_oz=105.822,
            height_in=24,
            head_circ_cm=46,
            BMI=17,
            bmi_percentile=50,
        ),
    ]
    base = {
        "patients": [patient],
        "visits": visits,
        "labs": [],
        "medications": [],
        "problem_list": [],
        "referrals": [],
    }
    augmented_visits = []
    for visit in visits:
        age = visit["age_in_days"]
        weight = visit["weight_oz"] / 35.274
        height = round(visit["height_in"] * 2.54, 3)
        bmi = "" if age / 30.4375 < 24 else weight / (height / 100) ** 2
        augmented_visits.append(
            row(
                package,
                "visits_augmented",
                patient_id=visit["patient_id"],
                visit_id=visit["visit_id"],
                sex="F",
                ethnicity="",
                race_1="",
                age_in_days=age,
                age_in_months=round(age / 30.4375, 2),
                age_in_years=round(age / 365.25, 3),
                weight_oz=visit["weight_oz"],
                weight_kg=weight,
                height_in=visit["height_in"],
                height_cm=height,
                head_circ_cm=visit["head_circ_cm"],
                bmi=bmi,
                bmi_percentile=50,
                bmi_category="normal",
                weight_z_score=0,
                height_z_score=0,
                bmi_z_score=0,
                head_circ_z_score=0,
                weight_for_length_z_score=0,
                weight_for_stature_z_score=0,
                weight_percentile=50,
                height_percentile=50,
                head_circ_percentile=50,
                weight_for_length_percentile=50,
                weight_for_stature_percentile=50,
                height_velocity_percentile=50,
                height_velocity_percentile_ep=50,
                height_velocity_percentile_ap=50,
                height_velocity_percentile_lp=50,
                stunting_flag=0,
                wasting_flag=0,
                underweight_flag=0,
                obesity_flag=0,
                encounter_type=visit["encounter_type"],
                orig_enc_source_Epic_yn=visit["orig_enc_source_Epic_yn"],
                **{f"enc_diag_{index}": visit[f"enc_diag_{index}"] for index in range(1, 34)},
            )
        )
    summaries = {}
    for metric in (
        "weight_z_score",
        "height_z_score",
        "bmi_z_score",
        "head_circ_z_score",
        "weight_for_length_z_score",
        "weight_for_stature_z_score",
    ):
        summaries |= {
            f"count_{metric}": 2,
            f"mean_{metric}": 0,
            f"std_{metric}": 0,
            f"min_{metric}": 0,
            f"max_{metric}": 0,
        }
    augmented_patient = row(
        package,
        "patients_augmented",
        patient_id="fictional-person",
        sex="F",
        ethnicity="",
        race_1="",
        healthy_flag=0,
        chronic_dx_flag=1,
        growth_dx_flag=1,
        ever_stunting_flag=0,
        ever_wasting_flag=0,
        ever_underweight_flag=0,
        ever_obesity_flag=0,
        visits_count=2,
        visits_count_pre_dx=0,
        min_visit_age_days=730,
        max_visit_age_days=800,
        visits_span_days=70,
        dx_age_years=round(730 / 365.25, 3),
        dx_age_years_e10=round(730 / 365.25, 3),
        **{
            f"dx_age_years_{suffix}": ""
            for suffix in (
                "e03_9", "e22_0", "e23_0", "e23_6", "e24", "e30_0", "e30_1", "e34_3",
                "e34_4", "e72_11", "k50", "k51", "k90_0", "n18", "n25_0", "p04_3", "p05",
                "p07", "p70", "p92_6", "q77", "q78_0", "q78_1", "q87_1", "q87_2", "q87_3",
                "q87_4", "q90", "q96", "q98_0", "q98_4", "q98_5",
            )
        },
        **summaries,
    )
    augmented = {"patients_augmented": [augmented_patient], "visits_augmented": augmented_visits}
    return package, base, copy.deepcopy(augmented), copy.deepcopy(augmented)


def evaluate(package, base, candidate_rows, reference_rows, **policy_overrides):
    return validate_derivation_parity(
        base,
        candidate_rows,
        reference_rows,
        package,
        candidate=implementation("candidate"),
        reference=implementation("reference"),
        policy=policy(**policy_overrides),
    )


def check(report, name):
    return next(item for item in report.checks if item.name == name)


def test_valid_fictional_rows_pass_deterministically_without_mutating_inputs():
    package, base, candidate_rows, reference_rows = fixtures()
    before = copy.deepcopy((base, candidate_rows, reference_rows, package))
    first = evaluate(package, base, candidate_rows, reference_rows)
    second = evaluate(package, base, candidate_rows, reference_rows)
    assert first.status is DerivationParityStatus.PASS
    assert first.to_json_bytes() == second.to_json_bytes()
    assert (base, candidate_rows, reference_rows, package) == before


@pytest.mark.parametrize(
    ("resource", "field", "value"),
    [
        ("visits_augmented", "weight_kg", 3.0),
        ("visits_augmented", "bmi_category", "obese"),
        ("patients_augmented", "healthy_flag", 1),
    ],
)
def test_candidate_field_mismatches_fail_and_are_aggregate_only(resource, field, value):
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows[resource][0][field] = value
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert report.status is DerivationParityStatus.FAIL
    parity = check(report, "reference_field_parity")
    assert parity.status is DerivationParityStatus.FAIL
    assert parity.compared_count == 251
    assert parity.mismatch_count >= 1
    assert "fictional" not in repr(report).lower()
    assert "fictional" not in report.to_json_bytes().decode()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: candidate["visits_augmented"].pop(),
        lambda package, base, candidate, reference: candidate["visits_augmented"].append(copy.deepcopy(candidate["visits_augmented"][0])),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].update({"unknown": "x"}),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("height_percentile", 101),
    ],
)
def test_structural_invalidity_fails_closed(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    report = evaluate(package, base, candidate_rows, reference_rows, minimum_visit_rows=3)
    assert report.status is DerivationParityStatus.FAIL
    assert any(item.reason_code == "STRUCTURAL_INVALID" for item in report.checks)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: (
            base["visits"][0].__setitem__("weight_oz", ""),
            candidate["visits_augmented"][0].__setitem__("weight_oz", ""),
            reference["visits_augmented"][0].__setitem__("weight_oz", ""),
            candidate["visits_augmented"][0].__setitem__("weight_kg", ""),
            reference["visits_augmented"][0].__setitem__("weight_kg", ""),
        ),
    ],
)
def test_missing_deterministic_evidence_is_unevaluable(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert report.status is DerivationParityStatus.UNEVALUABLE
    assert any(item.status is DerivationParityStatus.UNEVALUABLE for item in report.checks)


def test_underpowered_support_is_unevaluable():
    package, base, candidate_rows, reference_rows = fixtures()
    report = evaluate(package, base, candidate_rows, reference_rows, minimum_patient_rows=2)
    assert report.status is DerivationParityStatus.UNEVALUABLE
    assert check(report, "support").status is DerivationParityStatus.UNEVALUABLE
    assert check(report, "support").reason_code == "INSUFFICIENT_SUPPORT"


@pytest.mark.parametrize(
    ("resource", "field", "candidate_value", "reference_value"),
    [
        ("patients_augmented", "chronic_dx_flag", 0, 1),
        ("visits_augmented", "weight_outlier_flag", 0, 1),
        ("visits_augmented", "height_outlier_flag", 0, 1),
    ],
)
def test_reference_tolerance_does_not_relax_exact_flags(resource, field, candidate_value, reference_value):
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows[resource][0][field] = candidate_value
    reference_rows[resource][0][field] = reference_value
    report = evaluate(package, base, candidate_rows, reference_rows, reference_tolerance=1)
    assert check(report, "reference_field_parity").status is DerivationParityStatus.FAIL


@pytest.mark.parametrize("field", ("age_in_days", "weight_oz", "height_in"))
def test_nonzero_deterministic_tolerance_does_not_relax_copied_visit_fields(field):
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["visits_augmented"][0][field] += 1
    report = evaluate(package, base, candidate_rows, reference_rows, deterministic_tolerance=10)
    assert check(report, "visit_identity_projection").status is DerivationParityStatus.FAIL


@pytest.mark.parametrize(
    ("converted_field", "score_field", "score", "converted_value"),
    [
        ("weight_kg", "weight_z_score", 0, ""),
        ("height_cm", "height_z_score", 0, ""),
        ("weight_kg", "weight_z_score", 6, 2),
        ("height_cm", "height_z_score", 4, 50.8),
    ],
)
def test_visible_biv_evidence_rejects_jointly_wrong_conversion_presence(converted_field, score_field, score, converted_value):
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0][score_field] = score
        rows[0][converted_field] = converted_value
        if converted_value == "":
            rows[0]["bmi"] = ""
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "deterministic_unit_conversion").status is DerivationParityStatus.FAIL
    assert check(report, "reference_field_parity").status is DerivationParityStatus.PASS


@pytest.mark.parametrize(
    ("target", "operation", "shape_name"),
    [
        ("base", "missing", "base_shape"),
        ("candidate", "extra", "candidate_shape"),
        ("reference", "reordered", "reference_shape"),
    ],
)
def test_top_level_resource_mapping_errors_fail_the_owning_shape_check(target, operation, shape_name):
    package, base, candidate_rows, reference_rows = fixtures()
    rows = {"base": base, "candidate": candidate_rows, "reference": reference_rows}[target]
    if operation == "missing":
        rows.pop(next(iter(rows)))
    elif operation == "extra":
        rows["unexpected"] = []
    else:
        rows = {name: rows[name] for name in reversed(rows)}
        if target == "reference":
            reference_rows = rows
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "schema_contract").status is DerivationParityStatus.PASS
    assert check(report, shape_name).status is DerivationParityStatus.FAIL
    assert all(item.status is DerivationParityStatus.UNEVALUABLE for item in report.checks[4:])


def test_invalid_descriptor_does_not_fabricate_downstream_pass_checks():
    package, base, candidate_rows, reference_rows = fixtures()
    package["resources"].reverse()
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "schema_contract").status is DerivationParityStatus.FAIL
    assert all(item.status is DerivationParityStatus.UNEVALUABLE for item in report.checks[1:])


@pytest.mark.parametrize("value", (True, math.nan))
def test_noncanonical_numeric_scalars_fail_candidate_shape(value):
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["patients_augmented"][0]["visits_count"] = value
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "candidate_shape").status is DerivationParityStatus.FAIL


def test_large_integer_strings_are_parsed_losslessly_for_exact_parity():
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["patients_augmented"][0]["visits_count"] = "9007199254740993"
    reference_rows["patients_augmented"][0]["visits_count"] = "9007199254740992"
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "candidate_shape").status is DerivationParityStatus.PASS
    assert check(report, "reference_shape").status is DerivationParityStatus.PASS
    assert check(report, "reference_field_parity").status is DerivationParityStatus.FAIL


def test_overflowing_native_number_fails_candidate_shape_without_an_unavailable_error():
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["visits_augmented"][0]["weight_kg"] = 10**400
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "candidate_shape").status is DerivationParityStatus.FAIL


def test_hostile_numeric_scalars_fail_candidate_shape_without_invoking_user_methods():
    class HostileScalar:
        def __eq__(self, other):
            raise AssertionError("comparison must not be called")

        def __float__(self):
            raise AssertionError("conversion must not be called")

    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["patients_augmented"][0]["visits_count"] = HostileScalar()
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "candidate_shape").status is DerivationParityStatus.FAIL


def test_orphan_declared_base_foreign_key_fails_before_diagnosis_evidence_is_used():
    package, base, candidate_rows, reference_rows = fixtures()
    base["problem_list"].append(
        row(
            package,
            "problem_list",
            patient_id="fictional-orphan",
            problem_list_id="fictional-problem",
            noted_date_age_in_days=730,
            pl_diag="E10.9",
        )
    )
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "base_shape").status is DerivationParityStatus.FAIL
    assert check(report, "deterministic_patient_summaries").status is DerivationParityStatus.UNEVALUABLE


def test_permuted_valid_rows_produce_a_byte_identical_aggregate_report():
    package, base, candidate_rows, reference_rows = fixtures()
    expected = evaluate(package, base, candidate_rows, reference_rows).to_json_bytes()
    for rows in (base, candidate_rows, reference_rows):
        for values in rows.values():
            values.reverse()
    assert evaluate(package, base, candidate_rows, reference_rows).to_json_bytes() == expected


def test_blank_diagnosis_slots_do_not_create_diagnosis_age_summaries():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = ""
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update(
            {
                "healthy_flag": 1,
                "chronic_dx_flag": 0,
                "growth_dx_flag": 0,
                "visits_count_pre_dx": 2,
                "dx_age_years": "",
                "dx_age_years_e10": "",
            }
        )
    assert evaluate(package, base, candidate_rows, reference_rows).status is DerivationParityStatus.PASS


def test_bmi_gating_uses_base_age_not_candidate_age_conversion():
    package, base, candidate_rows, reference_rows = fixtures()
    candidate_rows["visits_augmented"][1].update({"age_in_months": 0, "bmi": ""})
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "deterministic_bmi").status is DerivationParityStatus.FAIL


def test_growth_summary_ignores_unrelated_diagnosis_before_growth_prefix():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = "A00.0"
        rows[1]["enc_diag_1"] = "E10.9"
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update(
            {
                "visits_count_pre_dx": 0,
                "dx_age_years": round(730 / 365.25, 3),
                "dx_age_years_e10": round(800 / 365.25, 3),
            }
        )
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "deterministic_patient_summaries").status is DerivationParityStatus.FAIL


def test_jointly_wrong_diagnosis_flags_fail_from_encounter_and_problem_list():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = ""
    base["problem_list"].append(
        row(
            package,
            "problem_list",
            patient_id="fictional-person",
            problem_list_id="fictional-problem",
            noted_date_age_in_days=730,
            pl_diag="E10.9",
        )
    )
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update({"chronic_dx_flag": 0, "growth_dx_flag": 0, "healthy_flag": 1})
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "clinical_flag_relationships").status is DerivationParityStatus.FAIL
    assert check(report, "reference_field_parity").status is DerivationParityStatus.PASS


def test_unknown_chronic_membership_remains_reference_dependent():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = ""
    base["problem_list"].append(
        row(
            package,
            "problem_list",
            patient_id="fictional-person",
            problem_list_id="fictional-problem",
            pl_diag="J45.909",
        )
    )
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update(
            {
                "chronic_dx_flag": 1,
                "growth_dx_flag": 0,
                "healthy_flag": 0,
                "visits_count_pre_dx": 2,
                "dx_age_years": "",
                "dx_age_years_e10": "",
            }
        )
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "clinical_flag_relationships").status is DerivationParityStatus.PASS
    assert report.status is DerivationParityStatus.PASS


def test_undated_growth_problem_makes_diagnosis_summary_unevaluable():
    package, base, candidate_rows, reference_rows = fixtures()
    for rows in (base["visits"], candidate_rows["visits_augmented"], reference_rows["visits_augmented"]):
        rows[0]["enc_diag_1"] = ""
    base["problem_list"].append(
        row(
            package,
            "problem_list",
            patient_id="fictional-person",
            problem_list_id="fictional-problem",
            noted_date_age_in_days="",
            pl_diag="E10.9",
        )
    )
    for rows in (candidate_rows["patients_augmented"], reference_rows["patients_augmented"]):
        rows[0].update(
            {
                "chronic_dx_flag": 0,
                "growth_dx_flag": 1,
                "healthy_flag": 0,
                "visits_count_pre_dx": 2,
                "dx_age_years": "",
                "dx_age_years_e10": "",
            }
        )
    report = evaluate(package, base, candidate_rows, reference_rows)
    assert check(report, "deterministic_patient_summaries").status is DerivationParityStatus.UNEVALUABLE
    assert report.status is DerivationParityStatus.UNEVALUABLE


def test_runtime_error_from_input_iterable_is_fixed_redacted_failure():
    class RaisingIterable:
        def __iter__(self):
            raise RuntimeError("sensitive caller detail")

    package, base, candidate_rows, reference_rows = fixtures()
    base["labs"] = RaisingIterable()
    with pytest.raises(DerivationParityUnavailable, match="^derivation parity evaluation is unavailable$"):
        evaluate(package, base, candidate_rows, reference_rows)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda package, base, candidate, reference: package["resources"].reverse(),
        lambda package, base, candidate, reference: package["resources"][0]["schema"]["fields"].reverse(),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("age_in_months", 0),
        lambda package, base, candidate, reference: candidate["visits_augmented"][1].__setitem__("height_cm", 0),
        lambda package, base, candidate, reference: candidate["visits_augmented"][1].__setitem__("bmi", ""),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("visits_span_days", 0),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("dx_age_years_e10", 0),
        lambda package, base, candidate, reference: candidate["patients_augmented"][0].__setitem__("mean_weight_z_score", 1),
        lambda package, base, candidate, reference: candidate["visits_augmented"][0].__setitem__("stunting_flag", 1),
    ],
)
def test_declared_deterministic_relationships_fail_when_contradicted(mutate):
    package, base, candidate_rows, reference_rows = fixtures()
    mutate(package, base, candidate_rows, reference_rows)
    assert evaluate(package, base, candidate_rows, reference_rows).status is DerivationParityStatus.FAIL


def test_projection_and_every_augmented_field_are_checked():
    for resource, expected_count in (("patients_augmented", 87), ("visits_augmented", 82)):
        package, base, candidate_rows, reference_rows = fixtures()
        fields = tuple(candidate_rows[resource][0])
        assert len(fields) == expected_count
        for field in fields:
            package, base, candidate_rows, reference_rows = fixtures()
            original = candidate_rows[resource][0][field]
            spec = next(item for item in field_specs(package, resource) if item["name"] == field)
            if spec["type"] in {"integer", "number"}:
                if spec.get("constraints", {}).get("enum") == [0, 1]:
                    value = 1 - original
                else:
                    value = 1 if original in {0, ""} else original + 1
            elif field.startswith("race_"):
                value = "White"
            elif spec.get("constraints", {}).get("enum"):
                value = next(value for value in spec["constraints"]["enum"] if value != original)
            else:
                value = "changed"
            candidate_rows[resource][0][field] = value
            report = evaluate(package, base, candidate_rows, reference_rows)
            assert check(report, "reference_field_parity").mismatch_count >= 1, (resource, field)
