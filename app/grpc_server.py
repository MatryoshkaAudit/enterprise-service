import logging

import grpc

from app.database import db_manager
from app.repositories.bom_repository import BOMRepository
from app.services.bom_service import BOMService
from protos.bom import bom_service_pb2, bom_service_pb2_grpc

logger = logging.getLogger(__name__)


def _node_dto_to_proto(node) -> bom_service_pb2.ComponentNode:
    return bom_service_pb2.ComponentNode(
        id=node.id,
        name=node.name,
        article=node.article,
        tier=node.tier,
        country_code=node.country_code,
        manufacturer=node.manufacturer,
        hs_code=node.hs_code,
        cost_rub=node.cost_rub,
        quantity=node.quantity,
        criticality=node.criticality,
        country_risk=node.country_risk,
        analog_availability=node.analog_availability,
        cfi_score=node.cfi_score,
        is_chokepoint=node.is_chokepoint,
        parent_id=node.parent_id or 0,
        children=[_node_dto_to_proto(c) for c in node.children],
        notes=node.notes,
    )


class BOMServiceServicer(bom_service_pb2_grpc.BOMServiceServicer):
    async def GetBOMTree(self, request, context):
        async with db_manager.get_session() as session:
            service = BOMService(BOMRepository(session))
            try:
                tree = await service.get_product_bom(request.product_id)
                root_proto = _node_dto_to_proto(tree.root_components[0]) if tree.root_components else None
                return bom_service_pb2.GetBOMTreeResponse(
                    product_id=tree.product_id,
                    product_name=tree.product_name,
                    root=root_proto,
                    total_cost_rub=tree.total_cost_rub,
                    paper_localization_pct=tree.paper_localization_pct,
                    defacto_localization_pct=tree.defacto_localization_pct,
                    total_components=tree.total_components_count,
                    chokepoints_count=tree.chokepoints_count,
                    overall_cfi_max=tree.overall_cfi_max,
                )
            except Exception as e:
                logger.error(f"gRPC GetBOMTree error: {e}")
                context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def SimulateAnalogSubstitution(self, request, context):
        async with db_manager.get_session() as session:
            service = BOMService(BOMRepository(session))
            try:
                res = await service.substitute_analog(request.component_id, request.analog_id)
                return bom_service_pb2.SimulateAnalogResponse(
                    success=res.success,
                    component_id=res.component_id,
                    old_cfi=res.old_cfi,
                    new_cfi=res.new_cfi,
                    new_defacto_localization_pct=res.new_defacto_localization_pct,
                    cost_delta_rub=res.cost_delta_rub,
                    redesign_investment_rub=res.redesign_investment_rub,
                    implementation_days=res.lead_time_days,
                    commentary=res.commentary,
                )
            except Exception as e:
                logger.error(f"gRPC SimulateAnalogSubstitution error: {e}")
                context.abort(grpc.StatusCode.INTERNAL, str(e))


async def serve_grpc(port: int = 50051) -> grpc.aio.Server:
    server = grpc.aio.server()
    bom_service_pb2_grpc.add_BOMServiceServicer_to_server(BOMServiceServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info(f"gRPC BOM server запущен на порту {port}")
    return server
