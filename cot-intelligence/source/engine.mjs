export function analyze(rows, window=52){
 const data=rows.map((r,i)=>{const lf=r.lfLong-r.lfShort, am=r.amLong-r.amShort;return {...r,lf,am,lfChange:i?lf-(rows[i-1].lfLong-rows[i-1].lfShort):null,amChange:i?am-(rows[i-1].amLong-rows[i-1].amShort):null}});
 const latest=data.at(-1); if(!latest)throw Error('No verified reports');
 const index=(key)=>{const v=data.slice(-window).map(r=>r[key]),min=Math.min(...v),max=Math.max(...v);return max===min?50:100*(latest[key]-min)/(max-min)};
 const sixWeeks=data.slice(-6),first=sixWeeks[0];
 const lfDelta=latest.lf-first.lf,amDelta=latest.am-first.am;
 const bias=sixWeeks.length<6?'معتدل':lfDelta>0&&amDelta>0?'Bullish':lfDelta<0&&amDelta<0?'Bearish':'معتدل';
 const biasReason=sixWeeks.length<6?'لا تتوفر ستة تقارير للمقارنة.':bias==='Bullish'?'صافي تموضع الفئتين ارتفع مقارنة بأول تقرير ضمن آخر 6 تقارير.':bias==='Bearish'?'صافي تموضع الفئتين انخفض مقارنة بأول تقرير ضمن آخر 6 تقارير.':'حركة صافي التموضع بين الفئتين غير متفقة أو ثابتة.';
 return {bias,biasReason,sixWeeks,lfDelta,amDelta,rows:data,latest,lfIndex:index('lf'),amIndex:index('am'),window,alignment:latest.lf>0&&latest.am>0?'Bullish':latest.lf<0&&latest.am<0?'Bearish':'Divergent'};
}
