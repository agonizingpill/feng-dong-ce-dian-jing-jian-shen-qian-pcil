from pydantic import BaseModel,Field
class BlindBatchInput(BaseModel):
    code:str=Field(min_length=3,max_length=60,pattern=r'\S')
    sweep_ids:list[int]=Field(min_length=1,max_length=200)
    mae_limit:float=Field(gt=0,le=10000,allow_inf_nan=False)
class BlindSubmitInput(BaseModel):
    batch_id:int
    layout_id:int
