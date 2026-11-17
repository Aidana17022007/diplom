export type ArteryViewport={kind:'reference'|'altered';left:number;top:number;width:number;height:number};
export type ArteryFrame={canvas:HTMLCanvasElement;views:ArteryViewport[]};

/** Top-left coordinates; both panes always use the same dimensions and scale. */
export function arteryViewports(width:number,height:number,compare:boolean):ArteryViewport[]{
  width=Number.isFinite(width)?Math.max(1,Math.floor(width)):1;
  height=Number.isFinite(height)?Math.max(1,Math.floor(height)):1;
  if(!compare||width<2||height<2)return [{kind:'altered',left:0,top:0,width,height}];
  const gap=Math.min(12,(width<560?height:width)-2);
  if(width<560){
    const pane=Math.max(1,Math.floor((height-gap)/2));
    return [{kind:'reference',left:0,top:0,width,height:pane},{kind:'altered',left:0,top:height-pane,width,height:pane}];
  }
  const pane=Math.max(1,Math.floor((width-gap)/2));
  return [{kind:'reference',left:0,top:0,width:pane,height},{kind:'altered',left:width-pane,top:0,width:pane,height}];
}
