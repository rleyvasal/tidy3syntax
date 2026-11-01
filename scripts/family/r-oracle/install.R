# The packages stats3's R oracle loads, at CRAN's current versions, as stats3's
# CI installs them, built from source with their dependencies. Some of R's
# parallel downloads fail now and then, so missing packages get three rounds.
options(timeout = 600)
repos <- "https://cloud.r-project.org"
pkgs <- c("dplyr", "jsonlite", "sandwich", "lmtest", "emmeans", "MASS", "quantreg", "car", "broom",
          "survival", "nnet", "mgcv", "lme4", "glmnet")
for (round in 1:3) {
    missing <- setdiff(pkgs, rownames(installed.packages()))
    if (!length(missing)) break
    install.packages(missing, repos = repos, Ncpus = 16)
}
old <- old.packages(repos = repos)
if (!is.null(old)) install.packages(rownames(old), repos = repos, Ncpus = 16)
for (p in pkgs) library(p, character.only = TRUE)
for (p in pkgs) cat(p, as.character(packageVersion(p)), "\n")
