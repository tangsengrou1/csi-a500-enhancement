$ErrorActionPreference = 'Stop'

$activeResult = 'Result/model_reports/linear_development_ic_sharpe_lowcorr_oriented_widegrid/evaluation_summary.csv'
Write-Output 'Waiting for the active IC-Sharpe experiment to finish...'
while (-not (Test-Path -LiteralPath $activeResult)) {
  Start-Sleep -Seconds 30
}

$experiments = @(
  @{
    Config = 'Code/config/linear_model_oldscreen_control_corr070.json'
    Output = 'Result/model_reports/linear_development_oldscreen_control_corr070'
    ModelDir = 'models/linear/development_oldscreen_control_corr070'
  },
  @{
    Config = 'Code/config/linear_model_oldscreen_corr050.json'
    Output = 'Result/model_reports/linear_development_oldscreen_corr050'
    ModelDir = 'models/linear/development_oldscreen_corr050'
  },
  @{
    Config = 'Code/config/linear_model_oldscreen_corr085.json'
    Output = 'Result/model_reports/linear_development_oldscreen_corr085'
    ModelDir = 'models/linear/development_oldscreen_corr085'
  },
  @{
    Config = 'Code/config/linear_model_oldscreen_ic_heavy.json'
    Output = 'Result/model_reports/linear_development_oldscreen_ic_heavy'
    ModelDir = 'models/linear/development_oldscreen_ic_heavy'
  },
  @{
    Config = 'Code/config/linear_model_oldscreen_performance_heavy.json'
    Output = 'Result/model_reports/linear_development_oldscreen_performance_heavy'
    ModelDir = 'models/linear/development_oldscreen_performance_heavy'
  }
)

foreach ($experiment in $experiments) {
  Write-Output "Starting $($experiment.Output)..."
  python -u Code/run_linear_model.py `
    --config $experiment.Config `
    --development-universe `
    --output $experiment.Output `
    --model-dir $experiment.ModelDir
  if ($LASTEXITCODE -ne 0) {
    throw "Experiment failed with exit code ${LASTEXITCODE}: $($experiment.Output)"
  }
}
