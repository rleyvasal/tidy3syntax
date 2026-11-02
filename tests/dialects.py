"""Dialects shaped like the four packages', with their exports given, so the tests import none of them."""

import re

from tidy3syntax import ASSIGN, Dialect

TIDY3_VERBS = frozenset({
    "add_count", "add_tally", "arrange", "case_match", "case_when", "chop", "complete", "count", "distinct",
    "drop", "drop_na", "expand", "fill", "filter", "filter_out", "get_dupes", "group_by", "head", "mutate",
    "nest", "pack", "pivot_longer", "pivot_wider", "pull", "recode_values", "reframe", "relocate", "rename",
    "replace_values", "replace_when", "select", "separate", "slice", "slice_head", "slice_max", "slice_min",
    "slice_sample", "slice_tail", "summarise", "summarize", "tally", "transmute", "ungroup", "unite", "unnest",
})

TIDY3 = Dialect(
    "tidy3",
    negation_calls=TIDY3_VERBS,
    ordered_calls={"distinct", "group_by", "mutate", "reframe", "rename", "select", "summarise", "summarize", "transmute"},
    settings={"add", "after", "before", "by", "drop", "groups", "keep", "keep_all", "name", "order_by", "sort",
              "weight", "where", "wt"},
    rule_calls={"case_when", "replace_when", "case_match", "recode_values", "replace_values"},
    rule_after_column={"replace_when", "case_match", "recode_values", "replace_values"},
    pipe_operators={">>"},
    exports=TIDY3_VERBS | {"tidy", "col", "n", "is_na", "starts_with"},
)

_VECTOR = re.compile(r"([(,]\s*)\[([^\[\]]*)\]\s*=(?!=)\s*([^,()]*(?:\([^()]*\))?)")


def tidy3a_vector_stage(source: str) -> str:
    """tidy3a's ``mutate([x, y] = value)``, simplified: a value with at most one level of parentheses."""
    return _VECTOR.sub(lambda m: f"{m.group(1)}{ASSIGN}([{m.group(2)}], {m.group(3).strip()})", source)


TIDY3A = Dialect(
    "tidy3a",
    negation_calls={"select", "filter", "mutate", "summarise", "summarize", "group_by", "pull", "arrange", "desc"},
    ordered_calls={"mutate", "group_by"},
    settings={"dropna", "axis"},
    stages=(tidy3a_vector_stage,),
    exports={"select", "filter", "mutate", "summarise", "group_by", "pull", "arrange", "desc", "read_array", "dot"},
)

PLOT3 = Dialect(
    "plot3",
    formula_calls={"facet_wrap", "facet_grid"},
    formula_keywords={"facets"},
    formula_backticks="strip",
    power_calls={"geom_function", "geom_vector_field"},
    unary_formula_calls={"facet_wrap", "facet_grid"},
    layer_calls={"geom_point", "geom_function", "facet_wrap", "facet_grid", "scale_x_log10", "theme_bw", "plot_layout"},
    exports={"ggplot", "aes", "geom_point", "geom_function", "geom_vector_field", "facet_wrap", "facet_grid",
             "scale_x_log10", "theme_bw", "plot_layout"},
)

STATS3_FUNCTIONS = frozenset({
    "bayes_lm", "bayes_glm", "multinom", "polr", "ansari_test", "aov", "bartlett_test", "binom_test",
    "chisq_test", "cohens_d", "cor_test", "eta_squared", "fisher_test", "fligner_test", "friedman_test", "glm",
    "glm_nb", "hedges_g", "kruskal_test", "ks_test", "levene_test", "lm", "manova", "mantelhaen_test",
    "mauchly_test", "mcnemar_test", "mood_test", "oneway_test", "p_adjust", "pairwise_prop_test",
    "pairwise_t_test", "pairwise_wilcox_test", "poisson_test", "prop_test", "prop_trend_test", "quade_test",
    "rlm", "rq", "shapiro_test", "t_test", "tukey_hsd", "var_test", "vcov_cl", "vcov_nw", "wilcox_test",
})

STATS3 = Dialect("stats3", formula_calls=STATS3_FUNCTIONS, prefixes={"stats3"}, exports=STATS3_FUNCTIONS)

ALL = (TIDY3, TIDY3A, PLOT3, STATS3)
