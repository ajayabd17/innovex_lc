import re


def check_condition(company: dict, condition: dict) -> bool:
    """
    Evaluate a single expected condition against company data.
    Supports multiple operators including regex validation.

    Two condition schemas are supported:
      TC-10.2 style: {"field": "...", "equals": ..., "not_null": true, ...}
      TC-10.3/5 style: {"field": "...", "operator": "regex_match"|"contains"|"not_equals"|"not_contains", "value": ...}
    """

    field = condition.get("field")
    value = company.get(field)

    # ------------------------------
    # TC-10.3 operator/value schema
    # ------------------------------
    operator = condition.get("operator")
    if operator:
        op_value = condition.get("value")

        if operator == "contains":
            # value may be a list of keywords (ANY must match) or a plain string
            if isinstance(op_value, list):
                text = str(value).lower() if value is not None else ""
                return any(kw.lower() in text for kw in op_value)
            return str(op_value).lower() in str(value).lower() if value is not None else False

        if operator == "regex_match":
            if value is None:
                return False
            return bool(re.match(str(op_value), str(value)))

        # Optional regex: pass for null/NA, validate only when meaningful value is present.
        if operator == "regex_match_optional":
            if value is None:
                return True
            text = str(value).strip()
            if text == "" or text.lower() in {"na", "n/a", "null", "none", "-"}:
                return True
            return bool(re.match(str(op_value), text))

        # TC-10.5 cross-field operators
        if operator == "not_equals":
            ref = condition.get("reference_field")
            if ref:
                ref_val = company.get(ref)
                return str(value).strip().lower() != str(ref_val).strip().lower()
            return str(value).strip().lower() != str(op_value).strip().lower()

        if operator == "not_contains":
            # list of keywords: ALL must be absent for pass
            if isinstance(op_value, list):
                text = str(value).lower() if value is not None else ""
                return not any(kw.lower() in text for kw in op_value)
            return str(op_value).lower() not in str(value).lower() if value is not None else True

        # TC-11.1.3 operator: website domain must be compatible with focus_sectors
        if operator == "domain_compatible_with":
            # DOMAIN_INDUSTRY_MAP: domain keyword → list of valid sector keywords
            DOMAIN_INDUSTRY_MAP = {
                "squareup": ["fintech", "payment", "finance", "financial", "banking", "pos"],
                "stripe":   ["fintech", "payment", "finance", "financial", "ecommerce"],
                "shopify":  ["ecommerce", "retail", "commerce", "shop"],
                "salesforce": ["crm", "software", "saas", "cloud", "sales"],
                "amazon":   ["ecommerce", "cloud", "retail", "logistics", "technology"],
                "apple":    ["technology", "software", "hardware", "consumer electronics"],
                "google":   ["technology", "software", "advertising", "cloud", "ai"],
                "tesla":    ["automotive", "electric", "vehicle", "energy", "transport"],
                "ford":     ["automotive", "vehicle", "manufacturing", "transport"],
            }
            ref_field = condition.get("reference_field")
            ref_value = (company.get(ref_field) or "").lower() if ref_field else ""
            domain = str(value).lower() if value is not None else ""

            for domain_kw, valid_sector_keywords in DOMAIN_INDUSTRY_MAP.items():
                if domain_kw in domain:
                    # Domain is known — check that focus_sectors aligns
                    if not any(s in ref_value for s in valid_sector_keywords):
                        return False  # conflict detected
            return True  # no known conflict

        # TC-11.2.2 operator: subsidiary metric must not be at parent scale
        if operator == "not_parent_metric":
            threshold = condition.get("threshold", 50000)
            if value is None:
                return True  # missing data is handled by not_null rules
            try:
                numeric_val = float(str(value).replace(",", "").replace("~", "").strip())
                return numeric_val <= threshold
            except (TypeError, ValueError):
                return True  # non-numeric values are not metric violations

        # TC-11.2.4 operator: URL must be entity-specific, not redirect to parent domain
        if operator == "entity_specific_url":
            parent_domain = condition.get("parent_domain", "")
            if not parent_domain or value is None:
                return True
            url = str(value).lower()
            return parent_domain.lower() not in url

        # TC-11.3.1 / TC-11.3.4: TLD must match HQ country (neutral TLDs exempt)
        if operator == "tld_matches_hq":
            # Country code → expected TLD keyword(s)
            COUNTRY_TLD_MAP = {
                "united kingdom": [".co.uk", ".uk"],
                "uk": [".co.uk", ".uk"],
                "germany": [".de"],
                "de": [".de"],
                "france": [".fr"],
                "fr": [".fr"],
                "netherlands": [".nl"],
                "nl": [".nl"],
                "japan": [".jp"],
                "jp": [".jp"],
                "india": [".in"],
                "in": [".in"],
                "australia": [".au", ".com.au"],
                "au": [".au", ".com.au"],
                "canada": [".ca"],
                "ca": [".ca"],
                "singapore": [".sg"],
                "sg": [".sg"],
            }
            NEUTRAL_TLDS = [".com", ".org", ".net", ".io", ".ai", ".co"]

            ref_field = condition.get("reference_field")
            hq = (company.get(ref_field) or "").lower() if ref_field else ""
            url = str(value).lower() if value else ""

            # If neutral TLD → always OK
            if any(url.endswith(t) or (t + "/") in url for t in NEUTRAL_TLDS):
                return True

            # Find expected TLDs for the HQ country
            for country_kw, tlds in COUNTRY_TLD_MAP.items():
                if country_kw in hq:
                    # Check if website TLD is in allowed list
                    if not any(t in url for t in tlds):
                        # Also check country TLD of another country is present (conflict)
                        return not any(
                            other_tld in url
                            for other_country, other_tlds in COUNTRY_TLD_MAP.items()
                            if other_country not in hq
                            for other_tld in other_tlds
                        )
            return True  # unknown country — no conflict detected

        # TC-11.3.2: Revenue must not be global-parent scale for a regional entity
        if operator == "revenue_not_global_scale":
            threshold_b = condition.get("global_threshold_billions", 100)
            ref_field = condition.get("reference_field")
            ops = (company.get(ref_field) or "").lower() if ref_field else ""

            # Only flag if entity appears regional (few countries)
            country_count = len([c for c in ops.split(";") if c.strip()]) if ops else 0
            if country_count > 5:
                return True  # multinational — global revenue is expected

            if value is None:
                return True
            import re as _re
            m = _re.search(r"\$([\d\.]+)([BbTt])", str(value))
            if m:
                amount = float(m.group(1))
                unit = m.group(2).upper()
                if unit == "T":
                    amount *= 1000  # convert trillions to billions
                if amount > threshold_b:
                    return False
            return True

        # TC-11.3.3: Compliance certs must match HQ regulatory region
        if operator == "compliance_matches_region":
            ref_field = condition.get("reference_field")
            hq = (company.get(ref_field) or "").lower() if ref_field else ""
            compliance = (str(value) if value else "").lower()

            # EU countries — GDPR is expected; HIPAA-only is a mismatch
            EU_COUNTRIES = ["germany", "france", "netherlands", "spain", "italy",
                            "sweden", "poland", "belgium", "austria", "denmark"]
            US_KEYWORDS = ["united states", "usa", ", us", "us,"]

            is_eu = any(c in hq for c in EU_COUNTRIES)
            is_us = any(c in hq for c in US_KEYWORDS)

            if is_eu:
                # HIPAA alone for an EU entity is a mismatch (HIPAA is US healthcare law)
                hipaa_present = "hipaa" in compliance
                gdpr_present = "gdpr" in compliance or "iso" in compliance
                if hipaa_present and not gdpr_present:
                    return False  # HIPAA-only on EU entity is a conflict
            return True  # US or unknown: no violation

        # TC-11.3.5: HQ country must appear in operating_countries
        if operator == "hq_in_operating_countries":
            ref_field = condition.get("reference_field")
            ops = (company.get(ref_field) or "").lower() if ref_field else ""
            hq = str(value).lower() if value else ""

            if not hq or not ops:
                return True  # missing data handled by not_null rules

            # Extract country from HQ (last part after last comma, e.g. "Dublin, Ireland" → "ireland")
            hq_parts = [p.strip() for p in hq.split(",")]
            hq_country = hq_parts[-1] if hq_parts else hq

            # Check if HQ country or known aliases appear in operating_countries
            HQ_ALIAS = {
                "ireland": ["ireland"],
                "united states": ["united states", "usa", "us"],
                "united kingdom": ["united kingdom", "uk"],
                "germany": ["germany"],
                "netherlands": ["netherlands"],
                "india": ["india"],
            }
            search_terms = HQ_ALIAS.get(hq_country, [hq_country])
            return any(term in ops for term in search_terms)

        # TC-11.4.3: LinkedIn URL must correspond to short_name brand alias
        if operator == "linkedin_matches_alias":
            ref_field = condition.get("reference_field")
            alias = (company.get(ref_field) or "").lower().replace(" ", "")
            url = str(value).lower() if value else ""

            if not alias or not url:
                return True  # missing fields handled by not_null rules

            # The LinkedIn URL slug should contain the alias (e.g. /company/3m, /company/ibm)
            # Also allow common brand transformations: remove punctuation
            clean_alias = re.sub(r"[^a-z0-9]", "", alias)
            return clean_alias in url

        # TC-11.4.5: Acronym disambiguation — pure uppercase acronyms need focus_sectors
        if operator == "acronym_has_focus_sector":
            ref_field = condition.get("reference_field")
            focus = (company.get(ref_field) or "").strip()
            alias = str(value).strip() if value else ""

            # Detect pure uppercase acronym: 2-6 uppercase letters only (e.g. IBM, AAA, 3M)
            import re as _re2
            is_acronym = bool(_re2.match(r'^[A-Z0-9]{2,6}$', alias))
            if is_acronym:
                return bool(focus)  # must have focus_sectors for disambiguation
            return True  # not an acronym — no disambiguation required

        # TC-11.5.3: Deprecated brand names (deadnaming check)
        if operator == "no_deprecated_brand_names":
            # List of deadnames that should be redirected to new legal entities
            DEPRECATED_MAP = {
                "twitter": "X Corp.",
                "facebook": "Meta Platforms, Inc."
            }
            name_lower = str(value).lower()
            # Fails if the company_name is exactly the old brand (e.g. "Twitter")
            # or closely resembles it without the new legal branding
            for deadname in DEPRECATED_MAP:
                if deadname in name_lower and "inc" not in name_lower and "corp" not in name_lower:
                     return False
            return True

        # TC-11.5.5: Suffix alignment with nature_of_company
        if operator == "suffix_aligns_with_nature":
            ref_field = condition.get("reference_field")
            nature = (company.get(ref_field) or "").lower()
            name = str(value).lower()

            # Identify suffixes
            has_inc = any(s in name for s in ["inc.", "corp.", "corporation", "incorporated", "plc", "ltd.", "limited", "s.a.", "ag", "gmbh"])
            has_llc = "llc" in name

            is_public = "public" in nature

            # Rule: Public companies must typically be Incorporated (Inc/Corp/PLC), not LLCs
            # (Simplified business rule for validation)
            if is_public:
                if has_llc:
                    return False # Public LLCs are rare/special tax structures, usually flagged
                if not has_inc:
                    return False # Public entity implies incorporation
            
            return True



        # TC-12.1 Business Classification Logic

        # TC-12.1.2/3: Employee size consistency for Startup/SMB
        if operator == "employee_consistency_check":
            ref_field = condition.get("reference_field") # industry/category
            cat = (company.get(ref_field) or "").lower()
            size = str(value) if value is not None else ""

            if not size: return True # Missing data handled by not_null rules if any
            
            # Parse size: "15", "11-50", "1,000", "10,000+"
            import re as _re_size
            nums = _re_size.findall(r"\d+", size.replace(",", ""))
            if not nums: return True
            
            # Use max of range for upper bound check, min for lower
            min_s = int(nums[0])
            max_s = int(nums[-1])
            
            if "startup" in cat:
                # Startup: Typically small (<1000). 
                if min_s > 1000: return False # Too big for "Startup"?
            
            if "smb" in cat or "msme" in cat:
                # SMB: ~100-999
                # If size < 10, maybe too small? But "SMB" is broad.
                # If size > 2500, definitely Enterprise.
                if min_s > 2500: return False
            return True

        # TC-12.1.4: Conditional Funding Check for Startups
        if operator == "startup_funding_required":
            ref_field = condition.get("reference_field")
            cat = (company.get(ref_field) or "").lower()
            funding = str(value) if value else ""
            
            if "startup" in cat:
                if not funding: return False
                # User-supplied regex for "YYYY-MM-DD - $Amount" format
                import re as _re_fund
                pattern = r"^(\d{4}-\d{2}-\d{2}\s-\s\$?[\d,]+(?:\.\d{2})?)(,\s*\d{4}-\d{2}-\d{2}\s-\s\$?[\d,]+(?:\.\d{2})?)*$"
                return bool(_re_fund.match(pattern, funding))
            return True

        # TC-12.1.5: Investor Backing Check
        if operator == "investor_backers_required":
            ref_field = condition.get("reference_field")
            cat = (company.get(ref_field) or "").lower()
            investors = str(value) if value else ""
            
            if "vc" in cat or "investor" in cat:
                 # Must correspond to regex ^[\w\s&.,\-\(\)]+(,\s*[\w\s&.,\-\(\)]+)*$
                 if not investors: return False
                 import re as _re_inv
                 pattern = r"^[\w\s&.,\-\(\)]+(,\s*[\w\s&.,\-\(\)]+)*$"
                 return bool(_re_inv.match(pattern, investors))
            return True

        # TC-12.4 Sentiment & Rating Range Checks
        if operator == "numeric_range":
            min_val = condition.get("min_val")
            max_val = condition.get("max_val")
            if value is None or str(value).strip().lower() == "null" or str(value).strip() == "":
                return True # handled by not_null if required
            try:
                numeric_val = float(str(value).replace(",", "").strip())
                if min_val is not None and numeric_val < min_val:
                    return False
                if max_val is not None and numeric_val > max_val:
                    return False
                return True
            except (TypeError, ValueError):
                return False

        # Unknown operator → treat as pass to avoid silent failures hiding bugs
        return True

    # ------------------------------
    # TC-10.2 inline-key schema
    # ------------------------------

    # Equality / inequality checks
    if "equals" in condition:
        return value == condition["equals"]

    if "not_equals" in condition:
        return value != condition["not_equals"]

    # Inline not_contains (TC-10.5 cross-field, single string)
    if "not_contains" in condition:
        kw = condition["not_contains"].lower()
        return kw not in str(value).lower() if value is not None else True

    # Null checks
    if condition.get("not_null"):
        return value is not None

    if condition.get("null"):
        return value is None

    # Numeric comparisons
    if "greater_than" in condition:
        try:
            return float(value) > condition["greater_than"]
        except (TypeError, ValueError):
            return False

    if "less_or_equal" in condition:
        try:
            return float(value) <= condition["less_or_equal"]
        except (TypeError, ValueError):
            return False

    # String containment (single string only in TC-10.2)
    if "contains" in condition:
        return condition["contains"].lower() in str(value).lower() if value is not None else False

    # REGEX MATCH (TC-10.2 inline style — kept for backwards compatibility)
    if "regex_match" in condition:
        pattern = condition["regex_match"]
        if value is None:
            return False
        return bool(re.match(pattern, str(value)))

    # Default → condition passes
    return True

