#pragma once
#include "object_frame.hpp"
#include "stage_camera.hpp"

namespace ss6 {
class AuxiliaryObjects;

// The courier and the thrown item have independent lifetimes. Picking up an
// item clears the slot immediately, even if the courier has not left yet.
class StageItemDelivery {
public:
    StageItemDelivery(); // 1b5090, once per match
    void start(int kind,int targetX,int fromRight,const StageCamera&); // 1b5800
    void visit(const GaugeState&,AuxiliaryObjects&,ObjectDrawQueue&); // priority 30, 1b51b8
    void clear(); // 1b5980, also called at round reset and on pickup
    void hideNextDraw(); // 1b59a0, both bodies in the menu
    bool busy() const {return busy_;} // 1b5af8
    int itemIndex() const {return floorKind_;} // 1b5960; -1 until an item lands
    float itemX() const; // 1b5970
    uint32_t itemCallback() const {return callback_;}
    bool courierActive() const {return courierActive_;}
    const AuxiliaryObject& courier() const {return courier_;}
    const AuxiliaryObject& item() const {return item_;}
private:
    void updateCourier(AuxiliaryObjects&);
    void updateItem(const GaugeState&,AuxiliaryObjects&);
    AuxiliaryObject courier_{},item_{};
    bool busy_=false,courierActive_=false;
    int floorKind_=-1,deliveryKind_=0,wanted_=0,current_=0,phase_=0;
    uint32_t callback_=0;
    float targetX_=0,startLeft_=0,startRight_=0;
};
}
