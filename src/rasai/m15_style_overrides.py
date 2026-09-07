"""Final M15 layout overrides for the legacy six-cell Score row."""

SCORE_LAYOUT_CSS = r"""
/* M15 score grid: legacy row has dimension, score, classification, coverage,
   confidence and consolidation. Keep short status tokens readable. */
.score-row{
  grid-template-columns:minmax(210px,1.45fr) minmax(150px,.72fr) minmax(125px,.72fr) minmax(86px,.48fr) minmax(125px,.68fr) minmax(145px,.78fr)!important;
  gap:10px!important;
}
.score-row>div{min-width:0}
.score-row .score-number{font-size:clamp(1.08rem,1.65vw,1.32rem)!important;line-height:1.15;white-space:nowrap;overflow-wrap:normal!important;word-break:normal!important}
.score-row>div:nth-child(n+3) strong{font-size:.91rem;line-height:1.25;overflow-wrap:normal!important;word-break:normal!important;hyphens:none}
.score-row>div:nth-child(4) strong,.score-row>div:nth-child(5) strong,.score-row>div:nth-child(6) strong{white-space:nowrap}
@media(max-width:1200px) and (min-width:821px){
  .score-row{grid-template-columns:minmax(200px,1.35fr) minmax(150px,.8fr) minmax(130px,.8fr)!important;align-items:start}
  .score-row>div:nth-child(n+4){padding-top:7px;border-top:1px solid #edf0f4}
}
@media(max-width:820px){
  .score-row{grid-template-columns:1fr!important}
  .score-row .score-number,.score-row>div:nth-child(n+3) strong{white-space:normal}
  .score-row>div:nth-child(n+4){padding-top:5px;border-top:0}
}
"""
