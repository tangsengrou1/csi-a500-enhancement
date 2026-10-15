$ErrorActionPreference = 'Stop'

python -u Code/run_linear_model.py `
  --config Code/config/linear_model_ic_return_lowcorr_widegrid.json `
  --development-universe `
  --output Result/model_reports/linear_development_ic_return_lowcorr_oriented_widegrid `
  --model-dir models/linear/development_ic_return_lowcorr_oriented_widegrid
if ($LASTEXITCODE -ne 0) {
  throw "IC-return experiment failed with exit code $LASTEXITCODE"
}

python -u Code/run_linear_model.py `
  --config Code/config/linear_model_ic_sharpe_lowcorr_widegrid.json `
  --development-universe `
  --output Result/model_reports/linear_development_ic_sharpe_lowcorr_oriented_widegrid `
  --model-dir models/linear/development_ic_sharpe_lowcorr_oriented_widegrid
if ($LASTEXITCODE -ne 0) {
  throw "IC-Sharpe experiment failed with exit code $LASTEXITCODE"
}
